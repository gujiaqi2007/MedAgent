"""LLM 封装：症状理解与自然语言生成。

设计原则：
- LLM 负责「理解与表达」：理解症状、生成更自然、更共情的回复。
- 规则引擎负责「风险判定与动作」：红/黄/绿级别、是否建议 120、是否通知监护人。
- 无 API Key 时完全离线，返回 None，调用方 fallback 到纯规则引擎。
"""
from __future__ import annotations

import json
import os
from typing import Any

from . import config

try:
    import httpx
    _HAS_HTTPX = True
except ImportError:  # pragma: no cover
    _HAS_HTTPX = False


def _client() -> httpx.Client | None:
    if not _HAS_HTTPX:
        return None
    # 复用一个 client，减少连接开销
    if not hasattr(_client, "instance"):
        _client.instance = httpx.Client(timeout=30.0)
    return _client.instance


def _system_prompt() -> str:
    return (
        "你是一位耐心的健康助手，面向老年人和慢病患者提供健康管理建议。"
        "你必须遵守以下安全约束：\n"
        "1. 你只能给出健康教育、缓解建议、就医指引，不能诊断疾病、不能开药。\n"
        "2. 危急情况（胸痛、呼吸困难、中风征兆、持续高热、大出血等）必须建议立即拨打 120 或就医。\n"
        "3. 回答要口语化、温和、有共情，避免使用医学术语和内部级别词（如‘一级’‘二级’‘三级’）。\n"
        "4. 必须包含免责声明：本建议仅供参考，不能替代医生诊断。\n"
        "5. 输出必须是纯文本，不要使用 Markdown 格式。"
    )


def _render_messages(user_text: str, rule_result: dict, user_context: dict | None) -> list[dict[str, str]]:
    ctx = json.dumps(user_context or {}, ensure_ascii=False)
    rr = json.dumps(rule_result, ensure_ascii=False, indent=2)
    user_content = (
        f"用户描述：{user_text}\n"
        f"用户上下文：{ctx}\n"
        f"规则引擎判定结果（你**必须**遵守其中的 level、suggest_120、notify 字段，不得修改）：\n{rr}\n\n"
        "请根据以上信息，用中文生成一段给用户的回复。要求：\n"
        "- 保持规则引擎确定的风险级别和动作；\n"
        "- 红色/黄色情况要共情且紧迫，绿色情况要温和；\n"
        "- 给出 1-3 个可能的追问，帮助用户补充信息；\n"
        "- 不要编造用户没有提到的症状；\n"
        "- 输出必须是纯文本，不要使用 Markdown、表格、代码块等格式；\n"
        "- 回答控制在 300 字以内，避免过长；\n"
        "- 不要使用‘一级’‘二级’‘三级’‘级别’等内部术语，用‘需要留意’‘需要重视’‘情况比较紧急’等大白话表达。\n\n"
        "请按以下 JSON 格式返回（不要带 Markdown 代码块）：\n"
        '{"title": "简短标题", "advice": "给用户的回复正文", "followups": ["追问1", "追问2"]}'
    )
    return [
        {"role": "system", "content": _system_prompt()},
        {"role": "user", "content": user_content},
    ]


def _clean_text(text: str) -> str:
    """去除 Markdown 标记和多余空行。"""
    import re
    text = re.sub(r"\*\*(.*?)\*\*", r"\1", text)      # **bold**
    text = re.sub(r"__(.*?)__", r"\1", text)          # __bold__
    text = re.sub(r"\*(.*?)\*", r"\1", text)          # *italic*
    text = re.sub(r"_(.*?)_", r"\1", text)            # _italic_
    text = re.sub(r"`{1,3}[^`]*`{1,3}", "", text)     # `code` / ```code
    text = re.sub(r"^#{1,6}\s*", "", text, flags=re.M)  # # heading
    text = re.sub(r"^[-*+]\s+", "", text, flags=re.M) # list
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _extract_json(text: str) -> str | None:
    """从 LLM 回复中提取 JSON 字符串（支持 ```json 代码块或直接 JSON）。"""
    import re
    # 优先匹配 ```json ... ``` 块
    m = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
    if m:
        return m.group(1)
    # 尝试匹配 { ... } 或 [ ... ] 区域
    m = re.search(r"(\{[\s\S]*\}|\[[\s\S]*\])", text)
    if m:
        return m.group(1)
    return None


def _parse_reply(text: str, rule_result: dict) -> dict:
    """从 LLM 回复中提取结构，若解析失败则返回规则结果。"""
    raw = text.strip()
    json_str = _extract_json(raw)

    data: dict[str, Any] = {}
    if json_str:
        try:
            data = json.loads(json_str)
        except json.JSONDecodeError:
            pass

    if not isinstance(data, dict):
        data = {}

    # 安全兜底：LLM 不能改变这些关键安全字段
    safe = {**rule_result}
    advice = data.get("advice") or data.get("reply") or raw
    safe["advice"] = _clean_text(str(advice))
    safe["title"] = _clean_text(data.get("title") or rule_result["title"])
    safe["followups"] = data.get("followups") or rule_result.get("followups", [])
    if not isinstance(safe["followups"], list):
        safe["followups"] = rule_result.get("followups", [])
    safe["llm_enhanced"] = True
    return safe


def call_llm(user_text: str, rule_result: dict, user_context: dict | None = None) -> dict | None:
    """
    调用 LLM 生成更自然的回答。
    返回结构化的分诊结果；若 LLM 不可用则返回 None，调用方应 fallback 到规则引擎。
    """
    api_key = config.DEEPSEEK_API_KEY
    if not api_key:
        return None

    client = _client()
    if client is None:
        return None

    messages = _render_messages(user_text, rule_result, user_context)
    payload = {
        "model": config.DEEPSEEK_MODEL,
        "messages": messages,
        "temperature": 0.6,
        "max_tokens": 4096,
    }

    try:
        response = client.post(
            f"{config.DEEPSEEK_BASE_URL}/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
        )
        response.raise_for_status()
        data = response.json()
        choice = data.get("choices", [{}])[0]
        content = choice.get("message", {}).get("content", "")
        if not content:
            return None
        return _parse_reply(content, rule_result)
    except Exception as e:  # noqa: BLE001
        # 任何异常都不应阻断规则引擎结果
        print(f"[llm] call failed: {e}")
        return None
