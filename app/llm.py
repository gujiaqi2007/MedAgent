"""LLM 模块：云端语义匹配与自然语言表达（可选，离线自动降级）。

安全原则（与本地规则库的关系）：
- 规则引擎决定 level / notify / suggest_120 / plain / source，LLM **不能**修改；
- LLM 只负责两件事：① 从规则库中选一条规则（match_rule）；② 改写 advice / title / followups 的措辞；
- 若 LLM 文本缺少规则要求的「关键指令」（如建议 120、通知监护人），自动补回规则原文，
  确保**冲突时以本地规则为准**。

配置位置：app/config.py（或项目根目录 .env 文件）。
  在 .env 中填写：
      DEEPSEEK_API_KEY=sk-xxxxxxxx
      DEEPSEEK_BASE_URL=https://api.deepseek.com
      DEEPSEEK_MODEL=deepseek-chat
  也兼容任意 OpenAI 兼容服务（SiliconFlow / OpenAI 等）。

未配置 API Key 时完全离线：match_rule()/call_llm() 返回 None，调用方自动使用纯规则结果。
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
        "你是一位耐心、专业的健康助手，面向老年人和慢病患者提供健康管理建议。"
        "你必须遵守以下安全约束：\n"
        "1. 你只能给出健康教育、缓解建议、就医指引，不能诊断疾病、不能开药、不承诺疗效。\n"
        "2. 规则引擎已给出风险级别与处置动作，你不得更改其风险级别、是否拨打 120、是否通知监护人。\n"
        "3. 危急情况（胸痛、呼吸困难、中风征兆、持续高热、大出血等）必须建议立即拨打 120 或就医。\n"
        "4. 回答要口语化、温和、有共情，避免使用医学术语和内部级别词（如‘一级’‘二级’‘三级’）。\n"
        "5. 不要编造用户没有提到的症状或病史。\n"
        "6. 必须包含免责声明：本建议仅供参考，不能替代医生诊断。\n"
        "7. 输出必须是纯文本，不要使用 Markdown 格式，控制在 300 字以内。"
    )


def _render_messages(
    user_text: str,
    rule_result: dict,
    user_context: dict | None,
    history: str = "",
) -> list[dict[str, str]]:
    ctx = json.dumps(user_context or {}, ensure_ascii=False)
    rr = json.dumps(rule_result, ensure_ascii=False, indent=2)
    history_part = f"会话上文：{history}\n" if history else ""
    user_content = (
        f"{history_part}"
        f"用户本轮描述：{user_text}\n"
        f"用户上下文：{ctx}\n"
        f"规则引擎判定结果（你**必须**遵守其中的 level、suggest_120、notify 字段，不得修改）：\n{rr}\n\n"
        "请根据以上信息，用中文生成一段给用户的回复。要求：\n"
        "- 保持规则引擎确定的风险级别和动作；\n"
        "- 红色/黄色情况要共情且紧迫，绿色情况要温和；\n"
        "- 给出 1-3 个可能的追问，帮助用户补充信息；\n"
        "- 不要编造用户没有提到的症状；\n"
        "- 输出必须是纯文本，不要使用 Markdown、表格、代码块等格式；\n"
        "- 回答控制在 300 字以内，避免过长；\n"
        "- 不要使用‘一级’‘二级’‘三级’‘级别’等内部术语，用‘需要留意’‘需要重视’‘情况比较紧急’等大白话表达；\n"
        "- 只有当规则结果中 notify 不是 none 时，才可以提到已通知家人；notify 为 none 时绝不要提通知家人。\n\n"
        "请按以下 JSON 格式返回（不要带 Markdown 代码块）：\n"
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
    """去除 Markdown 标记和多余空行。"""
    text = re.sub(r"\*\*(.*?)\*\*", r"\1", text)      # **bold**
    text = re.sub(r"__(.*?)__", r"\1", text)          # __bold__
    text = re.sub(r"\*(.*?)\*", r"\1", text)          # *italic*
    text = re.sub(r"_(.*?)_", r"\1", text)            # _italic_
    text = re.sub(r"`{1,3}[^`]*`{1,3}", "", text)     # `code` / ```code
    text = re.sub(r"^#{1,6}\s*", "", text, flags=re.M)  # # heading
    text = re.sub(r"^[-*+]\s+", "· ", text, flags=re.M)  # list
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _extract_json(text: str) -> str | None:
    """从 LLM 回复中提取 JSON 字符串（支持 ```json 代码块或直接 JSON）。"""
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


def _parse_reply(text: str, rule_result: dict) -> dict:
    """从 LLM 回复中提取结构，安全字段以规则结果为准。"""
    return _merge(_parse(text), rule_result)


_rules_digest_cache: str | None = None


def _rules_digest() -> str:
    """构造规则库摘要，供 LLM 做语义匹配（进程内缓存一次）。"""
    global _rules_digest_cache
    if _rules_digest_cache is None:
        from . import triage as _triage
        lines = []
        for c in _triage.CONDITIONS:
            kws = list(c.get("critical", [])) + list(c.get("keywords", []))
            lines.append(f"{c['id']}|{c.get('name', '')}|{c['level']}|{'、'.join(kws)}")
        _rules_digest_cache = "\n".join(lines)
    return _rules_digest_cache


def _chat(payload: dict, timeout: int = 60) -> str:
    data = _post_json(
        config.DEEPSEEK_BASE_URL.rstrip("/") + "/chat/completions",
        payload, config.DEEPSEEK_API_KEY, timeout=timeout,
    )
    return (data.get("choices") or [{}])[0].get("message", {}).get("content", "")


def match_rule(user_text: str, history: str = "") -> dict | None:
    """让 LLM 从规则库中做语义匹配，返回规则结果；不可用或失败返回 None。

    关键词只能覆盖有限说法，因此只要规则引擎尚未判红，就会调用本函数。
    LLM 只负责「选哪条规则」，级别与动作仍由选中的规则本身决定，
    避免 LLM 自由发挥风险判定。
    """
    if not enabled():
        return None

    from . import triage as _triage

    system = (
        "你是医疗分诊路由助手。你的唯一任务是从给定规则库中，选出与用户描述语义最匹配的一条规则。"
        "你不需要诊断，也不要编造规则库中不存在的 id。"
    )
    history_part = (
        f"会话上文（仅供理解指代，不是本轮主诉）：{history}\n\n" if history else ""
    )
    user_msg = (
        f"规则库（格式：id|名称|级别|关键词）：\n{_rules_digest()}\n\n"
        f"{history_part}"
        f"用户本轮描述：{user_text}\n\n"
        "请判断本轮描述对应哪条规则（可按语义理解，不必拘泥于关键词字面；"
        "若本轮只是「还是疼」「比刚才厉害」这类补充，可结合上文理解）。\n"
        "请只返回 JSON，不要加任何其他文字：\n"
        '{"rule_id": "<规则id>", "confidence": <0到1的小数>, "reason": "<20字以内的理由>"}\n'
        "如果没有任何规则匹配，rule_id 返回 null。"
    )

    try:
        content = _chat({
            "model": config.DEEPSEEK_MODEL,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user_msg},
            ],
            "temperature": 0.1,
            "max_tokens": 256,
        })
        if not content:
            return None

        json_str = _extract_json(content)
        if not json_str:
            return None
        data = json.loads(json_str)
        rule_id = data.get("rule_id")
        if not rule_id:
            return None

        # 校验 rule_id 必须真实存在于规则库
        cond = next((c for c in _triage.CONDITIONS if c.get("id") == rule_id), None)
        if cond is None:
            print(f"[llm] 返回了不存在的 rule_id: {rule_id}")
            return None

        result = _triage.build_result(cond)
        result["match_layer"] = "llm"
        result["llm_confidence"] = data.get("confidence")
        result["llm_reason"] = data.get("reason", "")
        return result
    except Exception as e:  # noqa: BLE001
        print(f"[llm] match_rule failed: {e}")
        return None


def call_llm(
    user_text: str,
    rule_result: dict,
    user_context: dict | None = None,
    history: str = "",
) -> dict | None:
    """
    调用 LLM 生成更自然的回答。
    返回结构化的分诊结果；若 LLM 不可用则返回 None，调用方应 fallback 到规则引擎。
    history 只用于让回答接得上上下文（如「还是疼，比刚才厉害」），不参与风险判定。
    """
    if not enabled():
        return None

    messages = _render_messages(user_text, rule_result, user_context, history)
    try:
        content = _chat({
            "model": config.DEEPSEEK_MODEL,
            "messages": messages,
            "temperature": 0.6,
            "max_tokens": 4096,
        })
        if not content:
            return None
        return _parse_reply(content, rule_result)
    except Exception as e:  # noqa: BLE001
        # 任何异常都不应阻断规则引擎结果
        print(f"[llm] call failed: {e}")
        return None


def enhance(user_text: str, rule_result: dict, user_context: dict | None = None) -> dict | None:
    """兼容旧接口：等价于 call_llm(user_text, rule_result, user_context)。"""
    return call_llm(user_text, rule_result, user_context)
