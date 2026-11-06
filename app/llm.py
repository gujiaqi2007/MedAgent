"""LLM 增强模块（可选）：调用 OpenAI 兼容接口，让回答更自然、更有共情。

安全原则（与本地规则库的关系）：
- 规则引擎决定 level / notify / suggest_120 / plain / source，LLM **不能**修改；
- LLM 只能改写 advice / title / followups 的措辞；
- 若 LLM 文本缺少规则要求的「关键指令」（如建议 120、通知监护人），自动补回规则原文，
  确保**冲突时以本地规则为准**。

配置位置：app/config.py（或项目根目录 .env 文件）。
  在 .env 中填写：
      DEEPSEEK_API_KEY=sk-xxxxxxxx
      DEEPSEEK_BASE_URL=https://api.deepseek.com
      DEEPSEEK_MODEL=deepseek-chat
  也兼容任意 OpenAI 兼容服务（SiliconFlow / OpenAI 等）。

未配置 API Key 时完全离线：enhance() 返回 None，调用方自动使用纯规则结果。
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from typing import Any

from . import config

_DEFAULT_OPTIONS = ["是", "否", "不清楚"]


def enabled() -> bool:
    return bool(getattr(config, "DEEPSEEK_API_KEY", ""))


def _system_prompt() -> str:
    return (
        "你是一位耐心、专业的健康助手，面向老年人和慢病患者。"
        "必须遵守：\n"
        "1. 只做健康教育、缓解建议与就医指引，不诊断、不开药、不承诺疗效。\n"
        "2. 规则引擎已给出风险级别与处置动作，你**不得更改**其风险级别、是否拨打 120、是否通知监护人。\n"
        "3. 危急情况（胸痛、呼吸困难、中风征兆、高热不退、大出血等）必须明确建议立即就医或拨打 120。\n"
        "4. 用大白话、口语化、有共情，避免医学术语和「一级/二级/三级」等内部词。\n"
        "5. 不要编造用户没有提到的症状或病史。\n"
        "6. 输出纯文本，不要 Markdown、表格或代码块。\n"
        "7. 控制在 300 字以内。"
    )


def _render_messages(user_text: str, rule_result: dict, user_context: dict | None) -> list[dict[str, str]]:
    ctx = json.dumps(user_context or {}, ensure_ascii=False)
    rr = json.dumps(rule_result, ensure_ascii=False, indent=2)
    user_content = (
        f"用户描述：{user_text}\n"
        f"用户上下文：{ctx}\n"
        f"规则引擎判定（你必须遵守其中的 level / suggest_120 / notify，不得修改）：\n{rr}\n\n"
        "请用中文生成给用户的回复，并严格按以下 JSON 返回（不要带代码块）：\n"
        '{"title": "简短标题", "advice": "给用户的回复正文", "followups": ["追问1", "追问2"]}'
    )
    return [
        {"role": "system", "content": _system_prompt()},
        {"role": "user", "content": user_content},
    ]


def _post_json(url: str, payload: dict, api_key: str, timeout: int = 60) -> dict:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _clean(text: str) -> str:
    text = re.sub(r"\*\*(.*?)\*\*", r"\1", text)
    text = re.sub(r"__(.*?)__", r"\1", text)
    text = re.sub(r"\*(.*?)\*", r"\1", text)
    text = re.sub(r"`{1,3}[^`]*`{1,3}", "", text)
    text = re.sub(r"^#{1,6}\s*", "", text, flags=re.M)
    text = re.sub(r"^[-*+]\s+", "· ", text, flags=re.M)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _extract_json(text: str) -> str | None:
    m = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
    if m:
        return m.group(1)
    m = re.search(r"(\{[\s\S]*\}|\[[\s\S]*\])", text)
    return m.group(1) if m else None


def _norm_followups(items) -> list[dict]:
    out = []
    for it in items or []:
        if isinstance(it, dict):
            out.append({"q": it.get("q") or it.get("question") or "",
                        "options": it.get("options") or _DEFAULT_OPTIONS})
        else:
            out.append({"q": str(it), "options": _DEFAULT_OPTIONS})
    return out


def _parse(text: str) -> dict:
    raw = text.strip()
    js = _extract_json(raw)
    if not js:
        return {}
    try:
        data = json.loads(js)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


def _merge(parsed: dict, rule: dict) -> dict:
    """把 LLM 结果并入规则结果，安全字段以规则为准。"""
    out = dict(rule)  # level / notify / suggest_120 / plain / source 等全部继承
    advice = _clean(str(parsed.get("advice") or parsed.get("reply") or ""))
    if not advice:
        return rule  # 解析失败，直接用规则

    # 关键指令补全：冲突时以本地规则为准
    if rule.get("suggest_120") and ("120" not in advice and "幺二零" not in advice):
        advice = (rule.get("advice") or "") + "\n\n" + advice
    elif rule.get("notify") in ("guardian", "immediate") and ("监护" not in advice and "家人" not in advice):
        advice = advice + "\n（已通知您的监护人）"

    out["advice"] = advice
    if parsed.get("title"):
        out["title"] = _clean(str(parsed["title"]))
    if isinstance(parsed.get("followups"), list) and parsed["followups"]:
        out["followups"] = _norm_followups(parsed["followups"])
    out["llm_enhanced"] = True
    return out


def enhance(user_text: str, rule_result: dict, user_context: dict | None = None) -> dict | None:
    """返回增强后的分诊结果；不可用/失败时返回 None（调用方回退规则结果）。"""
    if not enabled():
        return None
    try:
        payload = {
            "model": config.DEEPSEEK_MODEL,
            "messages": _render_messages(user_text, rule_result, user_context),
            "temperature": 0.5,
            "max_tokens": 1200,
        }
        data = _post_json(
            config.DEEPSEEK_BASE_URL.rstrip("/") + "/chat/completions",
            payload, config.DEEPSEEK_API_KEY,
        )
        content = (data.get("choices") or [{}])[0].get("message", {}).get("content", "")
        if not content:
            return None
        return _merge(_parse(content), rule_result)
    except (urllib.error.URLError, TimeoutError, OSError, ValueError, KeyError) as e:
        print(f"[llm] 调用失败，回退规则引擎：{e}")
        return None
