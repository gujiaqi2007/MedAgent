"""确定性医疗风险规则引擎（BASELINE.md §6）。

设计约束：
* 纯函数、零网络、零模型依赖 —— 本文件不得引入任何大模型 SDK 或 agent 模块；
* 规则数据放在 knowledge/rules.json，代码只负责匹配、否定处理、分级与修饰；
* 命中 EMERGENCY 时调用方必须短路，不得等待检索或追问。
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable

from contracts import RiskLevel, Slots, TriageResult, missing_slots

logger = logging.getLogger(__name__)

RULES_PATH = Path(__file__).resolve().parent.parent / "knowledge" / "rules.json"

SCREENING_NOTE = (
    "规则筛查只覆盖已定义的危险信号，未命中不代表安全；本结果不构成诊断，"
    "如有疑虑或症状加重，请及时就医。"
)

# 否定词（P4）：关键词前 6 个字符内出现即视为否定
NEGATORS = ("没有", "没", "无", "不", "未", "否认", "从来没", "并没有", "毫无", "并非")
NEGATOR_EXCEPTIONS = ("不仅", "不但", "不停", "不断", "不舒服")

HYPOTHETICAL_MARKERS = ("如果", "假如", "万一", "要是", "倘若")
CONSULT_MARKERS = ("会不会", "是不是", "要不要", "请问", "有没有可能")
PAST_MARKERS = ("以前", "去年", "曾经", "之前", "小时候", "多年前")
NOW_MARKERS = ("现在", "目前", "今天", "刚刚", "刚才", "这两天", "最近", "这几天")

SENTENCE_SPLIT = re.compile(r"[。！!？?；;\n]+")
TEMP_RE = re.compile(r"(\d{2}(?:\.\d)?)\s*(?:度|℃|°c|°C)")
FEVER_WORDS = ("发烧", "发热", "体温", "烧到", "低烧", "高烧")

_DOWNGRADE = {
    RiskLevel.EMERGENCY: RiskLevel.URGENT,
    RiskLevel.URGENT: RiskLevel.ROUTINE,
}


@dataclass
class _Match:
    rule: dict[str, Any]
    sentence: str
    terms: str
    level: RiskLevel


# --------------------------------------------------------------------------- #
# 规则加载与自检（§6.8）
# --------------------------------------------------------------------------- #
@lru_cache(maxsize=4)
def load_rules(path: str | None = None) -> tuple[dict[str, Any], ...]:
    """加载并校验规则。校验失败直接抛 ValueError，不允许静默跳过。"""
    rule_path = Path(path) if path else RULES_PATH
    if not rule_path.exists():
        raise ValueError(f"规则文件不存在：{rule_path}")

    with rule_path.open("r", encoding="utf-8") as handle:
        raw = json.load(handle)

    rules = raw["rules"] if isinstance(raw, dict) else raw
    problems: list[str] = []
    seen: set[str] = set()

    for item in rules:
        rid = str(item.get("id", "")).strip()
        if not rid:
            problems.append("存在缺少 id 的规则")
            continue
        if rid in seen:
            problems.append(f"{rid}: id 重复")
        seen.add(rid)
        if item.get("level") not in {lv.value for lv in RiskLevel}:
            problems.append(f"{rid}: level 非法（{item.get('level')}）")
        if not item.get("keywords"):
            problems.append(f"{rid}: keywords 为空")
        if not item.get("sources"):
            problems.append(f"{rid}: 缺少 sources")
        if not str(item.get("message", "")).strip():
            problems.append(f"{rid}: 缺少 message")

    if problems:
        raise ValueError("规则文件校验失败：\n- " + "\n- ".join(problems))

    return tuple(rules)


def rules_by_id(rules: Iterable[dict[str, Any]] | None = None) -> dict[str, dict[str, Any]]:
    rules = rules if rules is not None else load_rules()
    return {str(rule["id"]): rule for rule in rules}


# --------------------------------------------------------------------------- #
# 对外主函数
# --------------------------------------------------------------------------- #
def screen(text: str, slots: Slots | None = None, rules: Iterable[dict[str, Any]] | None = None) -> TriageResult:
    """对症状文本做风险筛查。纯函数，输入相同则输出相同。"""
    slots = slots or Slots()
    rule_list = list(rules) if rules is not None else list(load_rules())

    result = TriageResult(level=RiskLevel.INSUFFICIENT, screening_note=SCREENING_NOTE)
    result.missing_slots = missing_slots(slots)

    normalized = _normalize(text)
    if not normalized.strip():
        return result

    matches: list[_Match] = []
    skipped_hypothetical = False

    for sentence in _sentences(normalized):
        hypothetical = _is_hypothetical(sentence)
        past = _is_past(sentence)
        for rule in rule_list:
            if not _applies_to(rule, slots):
                continue
            terms = _match_rule(rule, sentence)
            if not terms:
                continue
            level = RiskLevel(rule["level"])
            if hypothetical and level == RiskLevel.EMERGENCY:
                # 假设 / 咨询句不升级为紧急，但仍提示需注意（P4）
                skipped_hypothetical = True
                continue
            if past:
                level = _DOWNGRADE.get(level, level)
            matches.append(_Match(rule=rule, sentence=sentence, terms=terms, level=level))

    # 数值体温：≥39℃ 直接按 R009 处理，避免"39.5 度"被关键词漏掉
    temp = _fever_temp(normalized)
    if temp is not None and temp >= 39.0 and any(word in normalized for word in FEVER_WORDS):
        r009 = next((r for r in rule_list if r["id"] == "R009"), None)
        if r009 and not any(m.rule["id"] == "R009" for m in matches):
            matches.append(
                _Match(
                    rule=r009,
                    sentence=f"体温 {temp}℃",
                    terms=f"{temp}℃",
                    level=RiskLevel(r009["level"]),
                )
            )

    if skipped_hypothetical:
        result.reasons.append("已识别到假设或咨询性表述，未按紧急情况处理；若确实出现该症状请重新描述。")

    # 汇总命中
    level = RiskLevel.INSUFFICIENT
    for match in matches:
        if match.rule["id"] not in result.matched_rules:
            result.matched_rules.append(str(match.rule["id"]))
            result.reasons.append(str(match.rule["message"]))
            if match.sentence and match.sentence != f"体温 {temp}℃":
                result.reasons[-1] += f"（依据：『{_trim(match.sentence, 28)}』）"
        for action in match.rule.get("action", []):
            if action not in result.red_flag_actions:
                result.red_flag_actions.append(action)
        for source in match.rule.get("sources", []):
            if source not in result.sources:
                result.sources.append(source)
        if match.level.rank > level.rank:
            level = match.level

    # 人群修饰（P5）：只升级与补问，不做诊断
    level, modifiers = _apply_modifiers(level, slots, normalized, result)

    # 没有紧急/较紧急命中时，才允许落到 ROUTINE / INSUFFICIENT（P2/P3）
    if level.rank < RiskLevel.URGENT.rank:
        level = RiskLevel.INSUFFICIENT if result.missing_slots else RiskLevel.ROUTINE

    result.level = level
    if level == RiskLevel.ROUTINE:
        result.reasons.append("未命中任何已定义的危险信号规则，且关键信息已收集。")
    elif level == RiskLevel.INSUFFICIENT and not matches:
        result.reasons.append("当前信息不足以完成风险筛查。")
    return result


# --------------------------------------------------------------------------- #
# 匹配细节
# --------------------------------------------------------------------------- #
def _normalize(text: str) -> str:
    if not text:
        return ""
    table = {"，": "，", "．": "。", " ": " ", "\u3000": " "}
    for old, new in table.items():
        text = text.replace(old, new)
    return text.strip()


def _sentences(text: str) -> list[str]:
    return [part.strip() for part in SENTENCE_SPLIT.split(text) if part.strip()]


def _negated(sentence: str, index: int) -> bool:
    window = sentence[max(0, index - 6) : index]
    if any(exception in window for exception in NEGATOR_EXCEPTIONS):
        return False
    return any(negator in window for negator in NEGATORS)


def _match_rule(rule: dict[str, Any], sentence: str) -> str | None:
    hits: list[str] = []
    for keyword in rule.get("keywords", []):
        keyword = str(keyword)
        if not keyword:
            continue
        start = 0
        found = False
        while True:
            index = sentence.find(keyword, start)
            if index < 0:
                break
            if not _negated(sentence, index):
                found = True
                break
            start = index + len(keyword)
        if found:
            hits.append(keyword)

    if len(hits) < int(rule.get("min_hits", 1)):
        return None

    need_context = int(rule.get("min_context", 0))
    if need_context:
        context_hits = [c for c in rule.get("context_hint", []) if c in sentence]
        if len(context_hits) < need_context:
            return None
    return "、".join(dict.fromkeys(hits))


def _applies_to(rule: dict[str, Any], slots: Slots) -> bool:
    need = rule.get("applies_to")
    if not need:
        return True
    tags: set[str] = set()
    if slots.age_group:
        tags.add(slots.age_group)
    if slots.pregnant:
        tags.add("pregnant")
    return bool(tags & set(need))


def _is_hypothetical(sentence: str) -> bool:
    if any(marker in sentence for marker in HYPOTHETICAL_MARKERS):
        return True
    if any(marker in sentence for marker in CONSULT_MARKERS):
        # 只有在没有明确第一人称症状陈述时才降级
        has_personal = re.search(
            r"(我|本人|孩子|宝宝|爸|妈|爷爷|奶奶|家人).{0,6}(疼|痛|烧|咳|吐|晕|麻|肿|出血|不舒服|难受)",
            sentence,
        )
        return not has_personal
    return False


def _is_past(sentence: str) -> bool:
    if not any(marker in sentence for marker in PAST_MARKERS):
        return False
    return not any(marker in sentence for marker in NOW_MARKERS)


def _fever_temp(text: str) -> float | None:
    values: list[float] = []
    for raw in TEMP_RE.findall(text):
        try:
            value = float(raw)
        except ValueError:
            continue
        if 34.0 <= value <= 43.0:
            values.append(value)
    return max(values) if values else None


def _apply_modifiers(
    level: RiskLevel, slots: Slots, text: str, result: TriageResult
) -> tuple[RiskLevel, list[str]]:
    modifiers: list[str] = []
    if slots.age_group == "infant":
        modifiers.append("infant")
    elif slots.age_group == "elderly":
        modifiers.append("elderly")
    if slots.pregnant:
        modifiers.append("pregnant")
    if slots.immunocompromised:
        modifiers.append("immunocompromised")
    for item in slots.chronic:
        modifiers.append(f"chronic:{item}")

    result.modifiers_applied = modifiers
    if not modifiers:
        return level, modifiers

    labels = {
        "infant": "1 岁以下婴儿",
        "elderly": "65 岁以上",
        "pregnant": "孕期",
        "immunocompromised": "免疫功能偏低",
    }

    if level == RiskLevel.ROUTINE:
        level = RiskLevel.URGENT
        reason = "因" + "、".join(
            labels.get(mod, mod.split(":", 1)[1]) for mod in modifiers[:2]
        ) + "，风险等级按更保守的标准上调。"
        result.reasons.append(reason)
    elif level == RiskLevel.INSUFFICIENT:
        result.reasons.append(
            "已注意到人群因素（"
            + "、".join(labels.get(mod, mod.split(":", 1)[1]) for mod in modifiers[:2])
            + "），但当前信息仍不足，需补充后再判断。"
        )
    return level, modifiers


def _trim(text: str, limit: int) -> str:
    text = text.strip()
    return text if len(text) <= limit else text[:limit] + "…"
