"""分诊规则引擎：基于关键词与医学规则的红/黄/绿分级。

设计原则（对应 baseline）：LLM 只负责「理解与表达」，风险判定由本规则引擎兜底，
避免大模型幻觉直接触发告警。规则表由医学专业人士维护并版本化。
"""
from __future__ import annotations

import json
import re
from pathlib import Path

_DATA_DIR = Path(__file__).parent / "data"

with (_DATA_DIR / "triage_rules.json").open("r", encoding="utf-8") as f:
    _RULES = json.load(f)

# 追加扩展规则（本地规则库 v2.1）
_extra_path = _DATA_DIR / "triage_rules_extra.json"
if _extra_path.exists():
    with _extra_path.open("r", encoding="utf-8") as f:
        _RULES["conditions"] = _RULES["conditions"] + json.load(f).get("conditions", [])

# 合并权威文献引用
_ref_path = _DATA_DIR / "references.json"
if _ref_path.exists():
    with _ref_path.open("r", encoding="utf-8") as f:
        _REFS = json.load(f)
    for _c in _RULES["conditions"]:
        _c.setdefault("references", _REFS.get(_c.get("id", ""), []))

CONDITIONS = _RULES["conditions"]
DISCLAIMER = _RULES.get("disclaimer", "")
SOURCE_NOTE = _RULES.get("source_note", "")

_LEVEL_RANK = {"red": 3, "yellow": 2, "green": 1}
_DEFAULT_OPTIONS = ["是", "否", "不清楚"]


def _normalize(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r"[\s,，。.!！?？、;；:：\"'“”‘’()（）\[\]【】]+", "", text)
    return text.lower()


def _match_score(text: str, keywords: list[str]) -> int:
    score = 0
    for kw in keywords:
        if kw and kw in text:
            score += 1 + (len(kw) // 2)
    return score


def _norm_followups(items) -> list[dict]:
    out = []
    for it in items or []:
        if isinstance(it, dict):
            out.append({"q": it.get("q", ""), "options": it.get("options") or _DEFAULT_OPTIONS})
        else:
            out.append({"q": str(it), "options": _DEFAULT_OPTIONS})
    return out


def triage(user_text: str) -> dict:
    """对一段用户描述做分诊，返回结构化结论（含通俗解释、权威来源、追问选项）。"""
    text = _normalize(user_text)
    if not text:
        return _fallback()

    best = None
    best_score = 0
    for cond in CONDITIONS:
        s = _match_score(text, cond.get("keywords", []))
        if s > best_score:
            best_score = s
            best = cond
        elif s == best_score and best is not None:
            if _LEVEL_RANK.get(cond["level"], 0) > _LEVEL_RANK.get(best["level"], 0):
                best = cond

    if best is None or best_score == 0:
        return _fallback()

    result = {
        "level": best["level"],
        "name": best.get("name", ""),
        "title": best.get("title", ""),
        "plain": best.get("plain", ""),
        "advice": best.get("advice", ""),
        "source": best.get("source", ""),
        "references": best.get("references", []),
        "suggest_120": bool(best.get("suggest_120", False)),
        "notify": best.get("notify", "none"),
        "followups": _norm_followups(best.get("followups", [])),
        "disclaimer": DISCLAIMER,
        "matched_condition_id": best.get("id", ""),
        "escalated": False,
        "escalate_note": "",
    }

    esc = best.get("escalate")
    if esc and _match_score(text, esc.get("keywords", [])) > 0:
        result["level"] = esc.get("level", "yellow")
        result["escalated"] = True
        result["escalate_note"] = esc.get("note", "")
        result["notify"] = "guardian"
        if result.get("escalate_note"):
            result["advice"] = result["escalate_note"] + "\n\n" + result["advice"]

    return result


def _fallback() -> dict:
    return {
        "level": "green",
        "name": "通用建议",
        "title": "请多留意身体感受",
        "plain": "我没太听清您具体哪里不舒服，您可以用一句话说说，比如「膝盖疼」「头晕」「发烧」。",
        "advice": "先多休息、喝点温水。如果出现胸口疼、喘不上气、说话不清、一边手脚没劲，请马上打 120 或叫家人。",
        "source": "通用健康提示",
        "suggest_120": False,
        "notify": "none",
        "followups": _norm_followups([
            {"q": "您最主要是哪里不舒服？", "options": ["膝盖/腿疼", "头晕", "发烧", "肚子疼"]},
            {"q": "这个不舒服持续多久了？", "options": ["今天", "两三天", "一周以上"]},
        ]),
        "disclaimer": DISCLAIMER,
        "matched_condition_id": "general",
        "escalated": False,
        "escalate_note": "",
    }


def triage_with_llm(user_text: str, user_context: dict | None = None) -> dict:
    """规则引擎兜底 + LLM 增强表达。

    先由本地规则确定风险级别与处置动作，再尝试用 LLM 优化措辞；
    LLM 不可用或失败时自动回退规则结果。冲突时以本地规则为准（见 llm._merge）。
    """
    rule_result = triage(user_text)
    try:
        from . import llm as _llm
        enhanced = _llm.enhance(user_text, rule_result, user_context)
    except Exception as e:  # noqa: BLE001
        print(f"[triage] llm error: {e}")
        enhanced = None
    return enhanced if enhanced else rule_result
