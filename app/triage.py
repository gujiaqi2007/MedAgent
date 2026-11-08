"""分诊规则引擎：三层匹配的红/黄/绿分级。

设计原则：LLM 只负责「理解与表达」，风险判定由本规则引擎兜底，
避免大模型幻觉直接触发或弱化告警。规则表由医学专业人士维护并版本化。

三层匹配：
  第一层「危急硬匹配」：命中 critical 关键词 → 强制红色，绝不漏判（宁多勿少）。
  第二层「规则库匹配」：按 keywords 计分选最佳规则，命中 escalate 则升级。
  第三层「LLM 语义匹配」：关键词覆盖不了所有口语说法时，由 LLM 从规则库中选一条，
                        只能升级、不能降级。

规则库参考：国家卫健委《急诊病人病情分级指导原则（试行）》、CTAS、
FAST/中风120、NEWS2、C-SSRS 等公开标准，为居家场景的保守版本。
"""
from __future__ import annotations

import json
import re
from pathlib import Path

_DATA_DIR = Path(__file__).parent / "data"

with (_DATA_DIR / "triage_rules.json").open("r", encoding="utf-8") as f:
    _RULES = json.load(f)

CONDITIONS = _RULES["conditions"]

# 追加扩展规则（本地规则库扩展包），只补充主库中不存在的 id，避免重复
_extra_path = _DATA_DIR / "triage_rules_extra.json"
if _extra_path.exists():
    with _extra_path.open("r", encoding="utf-8") as f:
        _existing_ids = {c.get("id") for c in CONDITIONS}
        for _c in json.load(f).get("conditions", []):
            if _c.get("id") not in _existing_ids:
                CONDITIONS.append(_c)
                _existing_ids.add(_c.get("id"))

# 合并权威文献引用
_ref_path = _DATA_DIR / "references.json"
if _ref_path.exists():
    with _ref_path.open("r", encoding="utf-8") as f:
        _REFS = json.load(f)
    for _c in CONDITIONS:
        _c.setdefault("references", _REFS.get(_c.get("id", ""), []))

DISCLAIMER = _RULES.get("disclaimer", "")
VERSION = _RULES.get("version", "unknown")
SOURCE_NOTE = _RULES.get("source_note", "")

# 级别优先级：红 > 黄 > 绿
_LEVEL_RANK = {"red": 3, "yellow": 2, "green": 1}
_DEFAULT_OPTIONS = ["是", "否", "不清楚"]

# 否定词：出现在关键词之前时，认为该关键词被否定（"我没有胸痛" 不应判红）
_NEGATIONS = ("没有", "没", "不", "无", "未", "非", "别", "否认")

# 口语中的程度/填充词：去掉后“心脏有点疼”能落到“心脏疼”等关键词上
_FILLERS = re.compile(
    r"有点儿|有一点|一点儿|有点|有些|一些|稍微|特别|非常|十分|挺|蛮|比较|很|得慌|这边|那里|那边|那儿"
)


def _normalize(text: str) -> str:
    """去空白、常见标点与口语填充词，便于关键词匹配。"""
    if not text:
        return ""
    text = re.sub(r"[\s,，。.!！?？、;；:：\"'“”‘’()（）\[\]【】]+", "", text)
    text = _FILLERS.sub("", text)
    return text.lower()


def _is_negated(text: str, kw: str) -> bool:
    """判断关键词是否被前置否定词修饰（如「没有胸痛」「不头晕」）。"""
    idx = text.find(kw)
    if idx <= 0:
        return False
    # 只看关键词前 3 个字符，避免跨句误判
    prefix = text[max(0, idx - 3):idx]
    return any(prefix.endswith(n) for n in _NEGATIONS)


def _match_score(text: str, keywords: list[str]) -> int:
    """返回匹配到的关键词加权得分（长词命中更可信）。"""
    score = 0
    for kw in keywords:
        if kw and kw in text and not _is_negated(text, kw):
            score += 1 + (len(kw) // 2)
    return score


def _norm_followups(items) -> list[dict]:
    """统一追问格式为 {q, options}，前端按卡片渲染。"""
    out = []
    for it in items or []:
        if isinstance(it, dict):
            out.append({"q": it.get("q", ""), "options": it.get("options") or _DEFAULT_OPTIONS})
        else:
            out.append({"q": str(it), "options": _DEFAULT_OPTIONS})
    return out


def build_result(cond: dict) -> dict:
    """由规则生成标准结果结构。"""
    return {
        "level": cond["level"],
        "name": cond.get("name", ""),
        "title": cond.get("title", ""),
        "plain": cond.get("plain", ""),
        "advice": cond.get("advice", ""),
        "source": cond.get("source", ""),
        "references": cond.get("references", []),
        "suggest_120": bool(cond.get("suggest_120", False)),
        "notify": cond.get("notify", "none"),
        "followups": _norm_followups(cond.get("followups", [])),
        "disclaimer": DISCLAIMER,
        "matched_condition_id": cond.get("id", ""),
        "category": cond.get("category", ""),
        "escalated": False,
        "escalate_note": "",
        "match_layer": "",
    }


def _match_critical(text: str) -> dict | None:
    """第一层：危急关键词硬匹配。命中即强制红色，同分取级别更高者。"""
    best = None
    best_score = 0
    for cond in CONDITIONS:
        crit = cond.get("critical")
        if not crit:
            continue
        s = _match_score(text, crit)
        if s > best_score:
            best_score = s
            best = cond
        elif s == best_score and s > 0 and best is not None:
            if _LEVEL_RANK.get(cond["level"], 0) > _LEVEL_RANK.get(best["level"], 0):
                best = cond
    if best is None:
        return None
    result = build_result(best)
    result["match_layer"] = "critical"
    return result


def _match_rules(text: str) -> tuple[dict | None, int]:
    """第二层：规则库匹配。

    选择策略「以最危险的信号为准」：优先取级别最高者；同级别时取匹配分最高者。
    （不能按分数优先——否则多个轻症关键词累加会盖过单次命中的重症。）

    返回 (结果 或 None, 选中规则的匹配分)。
    """
    best = None
    best_score = 0
    best_rank = 0
    for cond in CONDITIONS:
        s = _match_score(text, cond.get("keywords", []))
        if s == 0:
            continue
        rank = _LEVEL_RANK.get(cond["level"], 0)
        # 级别优先；同级别再看匹配分
        if rank > best_rank or (rank == best_rank and s > best_score):
            best_rank, best_score, best = rank, s, cond

    if best is None:
        return None, 0

    result = build_result(best)
    result["match_layer"] = "rules"

    # 绿色/黄色条件的升级：命中加重关键词 → 提升级别
    esc = best.get("escalate")
    if esc and _match_score(text, esc.get("keywords", [])) > 0:
        result["level"] = esc.get("level", "yellow")
        result["escalated"] = True
        result["escalate_note"] = esc.get("note", "")
        result["notify"] = "guardian"
        if result["escalate_note"]:
            result["advice"] = result["escalate_note"] + "\n\n" + result["advice"]

    return result, best_score


def triage(user_text: str, history: str = "") -> dict:
    """对一段用户描述做分层分诊（关键词 + LLM 语义），返回结构化结论。

    user_text: 用户最新一条消息（当前正在说的）
    history:   同一会话此前的用户消息（用于跨句补充与安全兜底）

    匹配策略（安全原则：以最危险的信号为准，只升不降）：
      第一层 · 危急硬匹配   → 对「最新消息 + 历史」全文匹配，命中即强制红色
                              （确定性，不交给 LLM；跨句补充细节也不会漏）
      第二层 · 关键词匹配   → 分别对「最新消息」和「全文」匹配，取级别更高者；
                              同级别时优先当前主诉，保证回答聚焦用户正在问的事
      第三层 · LLM 语义匹配 → 只要尚未判红就始终参与（关键词覆盖不了所有口语说法），
                              由 LLM 从规则库中选一条规则，且只能升级

    返回字段：
      level: red | yellow | green
      title, name, plain, advice, source, references, suggest_120, notify,
      followups, disclaimer, matched_condition_id, category, escalated,
      escalate_note, match_layer
    """
    text = _normalize(user_text)
    if not text:
        return _fallback()

    full_text = _normalize(f"{history} {user_text}") if history else text

    # ── 第一层：危急硬匹配对全文做（命中即红，绝不交给 LLM）──
    critical = _match_critical(full_text)
    if critical is not None:
        return critical

    # ── 第二层：关键词匹配 ──
    # 当前主诉的结果
    kw_latest = _match_rules(text)[0]
    # 全文（含历史）的结果，用于捕捉此前出现过的更危险信号
    kw_full = _match_rules(full_text)[0] if full_text != text else kw_latest

    # 以最危险的信号为准：全文级别更高则采用全文结果；同级别保留当前主诉
    kw_result = kw_latest
    if kw_full is not None and (
        kw_result is None
        or _LEVEL_RANK.get(kw_full["level"], 0) > _LEVEL_RANK.get(kw_result["level"], 0)
    ):
        kw_result = kw_full

    # 关键词命中红色时已是最危险信号，无需再问 LLM（省一次调用与延迟）
    if kw_result is not None and kw_result["level"] == "red":
        return kw_result

    # ── 第三层：LLM 语义匹配（始终参与，只能升级，不能降级）──
    # 关键词只能覆盖有限说法（“心脏有点疼”“胸口闷得慌”“嘴角有点歪”……），
    # 因此只要不是已经判红，都让 LLM 从规则库中做一次语义匹配。
    # LLM 只负责“选哪条规则”，级别与动作仍由规则本身决定。
    from . import llm as _llm
    llm_result = _llm.match_rule(user_text, history)

    if llm_result is not None:
        if kw_result is None:
            return llm_result
        if _LEVEL_RANK.get(llm_result["level"], 0) > _LEVEL_RANK.get(kw_result["level"], 0):
            return llm_result

    if kw_result is not None:
        return kw_result

    # 全部未命中 → 保守兜底
    return _fallback()


def _fallback() -> dict:
    return {
        "level": "green",
        "name": "通用建议",
        "title": "请多留意身体感受",
        "plain": "我没太听清您具体哪里不舒服，您可以用一句话说说，比如「膝盖疼」「头晕」「发烧」。",
        "advice": "感谢您的描述。目前没有识别到明确的危急信号，建议：多休息、注意补充水分、清淡饮食，并继续观察症状变化。若症状持续、加重，或出现胸痛、呼吸困难、言语不清、一侧无力等，请立即拨打 120 或联系监护人。",
        "source": "通用健康提示",
        "references": [],
        "suggest_120": False,
        "notify": "none",
        "followups": _norm_followups([
            {"q": "您最主要是哪里不舒服？", "options": ["膝盖/腿疼", "头晕", "发烧", "肚子疼"]},
            {"q": "这个不舒服持续多久了？", "options": ["今天", "两三天", "一周以上"]},
        ]),
        "disclaimer": DISCLAIMER,
        "matched_condition_id": "general",
        "category": "",
        "escalated": False,
        "escalate_note": "",
        "match_layer": "fallback",
    }


def triage_with_llm(user_text: str, user_context: dict | None = None, history: str = "") -> dict:
    """规则引擎兜底 + LLM 增强表达的分诊入口。

    先由规则引擎确定风险级别与动作，再尝试用 LLM 生成更自然、更共情的回答。
    若 LLM 不可用或失败，自动 fallback 到规则引擎结果，保证服务可用。
    """
    rule_result = triage(user_text, history)
    # 延迟导入，避免循环依赖
    from . import llm as _llm
    enhanced = _llm.call_llm(user_text, rule_result, user_context, history)
    return enhanced if enhanced is not None else rule_result
