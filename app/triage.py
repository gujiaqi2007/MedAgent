"""分诊规则引擎：基于关键词与医学规则的红/黄/绿分级。

设计原则（对应 baseline）：LLM 只负责「理解与表达」，风险判定由本规则引擎兜底，
避免大模型幻觉直接触发告警。规则表由医学专业人士维护并版本化。
"""
from __future__ import annotations

import json
import re
from pathlib import Path

_RULES_PATH = Path(__file__).parent / "data" / "triage_rules.json"

# 加载规则（进程启动一次）
with _RULES_PATH.open("r", encoding="utf-8") as f:
    _RULES = json.load(f)

CONDITIONS = _RULES["conditions"]
DISCLAIMER = _RULES.get("disclaimer", "")

# 级别优先级：红 > 黄 > 绿
_LEVEL_RANK = {"red": 3, "yellow": 2, "green": 1}


def _normalize(text: str) -> str:
    """去空白与常见标点，便于关键词匹配。"""
    if not text:
        return ""
    text = re.sub(r"[\s,，。.!！?？、;；:：\"'“”‘’()（）\[\]【】]+", "", text)
    return text.lower()


def _match_score(text: str, keywords: list[str]) -> int:
    """返回匹配到的关键词数量（加权：长词命中更可信）。"""
    score = 0
    for kw in keywords:
        if kw and kw in text:
            score += 1 + (len(kw) // 2)
    return score


def triage(user_text: str) -> dict:
    """对一段用户描述做分诊，返回结构化结论。

    返回字段：
      level: red | yellow | green
      title, name, advice, suggest_120, notify, followups, disclaimer,
      matched_condition_id, escalated (bool), escalate_note
    """
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
            # 同分取更高级别
            if _LEVEL_RANK.get(cond["level"], 0) > _LEVEL_RANK.get(best["level"], 0):
                best = cond

    if best is None or best_score == 0:
        return _fallback()

    result = {
        "level": best["level"],
        "name": best.get("name", ""),
        "title": best.get("title", ""),
        "advice": best.get("advice", ""),
        "suggest_120": bool(best.get("suggest_120", False)),
        "notify": best.get("notify", "none"),
        "followups": best.get("followups", []),
        "disclaimer": DISCLAIMER,
        "matched_condition_id": best.get("id", ""),
        "escalated": False,
        "escalate_note": "",
    }

    # 绿色条件的升级：命中加重关键词 → 升级为黄色
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
        "advice": "感谢您的描述。目前没有识别到明确的危急信号，建议：多休息、注意补充水分、清淡饮食，并继续观察症状变化。若症状持续、加重，或出现胸痛、呼吸困难、言语不清、一侧无力等，请立即拨打 120 或联系监护人。",
        "suggest_120": False,
        "notify": "none",
        "followups": ["您目前最主要的不适是什么？", "症状持续多久了？", "是否正在服用相关药物？"],
        "disclaimer": DISCLAIMER,
        "matched_condition_id": "general",
        "escalated": False,
        "escalate_note": "",
    }


def triage_with_llm(user_text: str, user_context: dict | None = None) -> dict:
    """规则引擎兜底 + LLM 增强表达的分诊入口。

    先由规则引擎确定风险级别与动作，再尝试用 LLM 生成更自然、更共情的回答。
    若 LLM 不可用或失败，自动 fallback 到规则引擎结果，保证服务可用。
    """
    rule_result = triage(user_text)
    # 延迟导入，避免循环依赖
    from . import llm as _llm
    enhanced = _llm.call_llm(user_text, rule_result, user_context)
    return enhanced if enhanced is not None else rule_result
