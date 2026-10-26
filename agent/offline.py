"""离线演示模式（BASELINE.md §10.5）。

只做三件事：生成追问、拼装报告、生成紧急卡。
必须在界面上显性标注"未调用大模型"，不允许伪装成模型推理。
"""

from __future__ import annotations

from typing import Any

from contracts import (
    SLOT_LABELS,
    SLOT_QUESTIONS,
    KnowledgeHit,
    RiskLevel,
    Slots,
    TriageResult,
)

OFFLINE_NOTICE = "离线演示模式：本报告由本地规则与固定模板生成，未调用大语言模型。"

DEFAULT_RED_FLAGS = [
    "意识改变、抽搐或叫不醒",
    "呼吸困难、口唇发紫",
    "持续胸部压榨性疼痛",
    "大量出血、呕血或黑便",
    "症状在数小时内明显加重",
]


def render_ask(missing: list[str], ask_count: int = 0) -> str:
    """按追问轮次轮换问法，避免复读机。"""
    if not missing:
        return "我还需要了解一些情况，能再多说一点吗？"
    slot = missing[0]
    variants = SLOT_QUESTIONS.get(slot)
    if not variants:
        return f"能再补充一下{SLOT_LABELS.get(slot, slot)}吗？"
    styles = ("direct", "choice", "reason")
    style = styles[min(ask_count, len(styles) - 1)]
    text = variants.get(style) or variants["direct"]

    extra = ""
    if len(missing) >= 2:
        nxt = missing[1]
        extra = f"\n\n（之后还想确认一下{SLOT_LABELS.get(nxt, nxt)}。）"
    return text + extra


def build_report(
    slots: Slots,
    triage: TriageResult,
    hits: list[KnowledgeHit],
    degraded_reason: str = "",
) -> dict[str, Any]:
    """按 contracts §5.6 的 schema 拼装报告。"""
    level = triage.level

    collected: dict[str, Any] = {
        "duration": slots.duration or "未提供",
        "severity": f"{slots.severity}/10" if slots.severity is not None else "未提供",
        "associated": list(slots.associated) or ["未提供"],
        "background": _background(slots) or ["未提供"],
    }

    report: dict[str, Any] = {
        "chief_complaint": slots.chief_complaint or "未明确描述",
        "collected": collected,
        "missing": [SLOT_LABELS.get(item, item) for item in triage.missing_slots],
        "risk": {
            "level": level.value,
            "basis": list(triage.reasons) or [triage.screening_note],
        },
        "next_steps": _next_steps(level, triage),
        "knowledge_summary": [
            {
                "id": hit.id,
                "title": hit.title,
                "url": hit.url,
                "one_line": hit.summary,
            }
            for hit in hits
        ],
        "red_flags_to_watch": list(DEFAULT_RED_FLAGS),
        "limitations": _limitations(triage, hits, degraded_reason),
    }
    return report


def render_emergency(triage: TriageResult) -> str:
    actions = triage.red_flag_actions or [
        "立即拨打 120 或前往最近医院急诊",
        "不要自行驾车前往",
        "保持安静，等待救援",
    ]
    lines = [RiskLevel.EMERGENCY.first_sentence, "", "**现在请这样做：**"]
    lines += [f"{idx}. {action}" for idx, action in enumerate(actions, 1)]
    if triage.reasons:
        lines += ["", "**判断依据（规则筛查）：**"]
        lines += [f"- {reason}" for reason in triage.reasons]
    lines += ["", "> 以上为规则筛查结果，不构成诊断；请以接诊医生的判断为准。"]
    return "\n".join(lines)


def _background(slots: Slots) -> list[str]:
    items: list[str] = []
    if slots.age_group:
        items.append(
            {
                "infant": "1 岁以下",
                "child": "儿童/青少年",
                "adult": "成人",
                "elderly": "65 岁以上",
            }.get(slots.age_group, slots.age_group)
        )
    if slots.sex:
        items.append({"female": "女性", "male": "男性"}.get(slots.sex, slots.sex))
    if slots.pregnant:
        items.append("孕期")
    if slots.chronic:
        items.append("基础病：" + "、".join(slots.chronic))
    if slots.immunocompromised:
        items.append("免疫功能偏低")
    return items


def _next_steps(level: RiskLevel, triage: TriageResult) -> list[str]:
    if level == RiskLevel.EMERGENCY:
        return list(triage.red_flag_actions) or ["立即拨打 120 或前往最近医院急诊"]
    if level == RiskLevel.URGENT:
        steps = list(triage.red_flag_actions)
        if not steps:
            steps = ["24 小时内前往医院就诊（可挂内科/全科）"]
        steps.append("就诊时带上症状时间线与用过的药物清单")
        steps.append("如出现意识改变、呼吸困难或疼痛剧烈加重，立即转急诊")
        return steps
    if level == RiskLevel.ROUTINE:
        return [
            "先居家观察 24–48 小时，记录症状变化（时间、程度、诱因）",
            "保证休息与饮水，暂不自行叠加多种药物",
            "若症状持续不缓解或出现下方「需警惕的变化」，及时就医",
        ]
    return [
        "补充上方「仍缺失的信息」后可重新评估",
        "如症状加重或出现下方「需警惕的变化」，请直接就医",
        "不确定时，可先电话咨询社区医院或线上问诊",
    ]


def _limitations(triage: TriageResult, hits: list[KnowledgeHit], degraded_reason: str) -> list[str]:
    items = [
        triage.screening_note or "规则筛查不等于诊断。",
        "本报告用于健康信息整理与就医导航，不能替代医生面诊。",
        "知识库条目数量有限，未覆盖的主题不代表没有风险。",
    ]
    if not hits:
        items.append("本次未检索到可靠知识条目，相关建议仅基于规则筛查。")
    pending = [hit for hit in hits if hit.link_level == "site"]
    if pending:
        items.append("部分来源为机构站点入口，建议在站内检索原文核对。")
    if degraded_reason:
        items.append(degraded_reason)
    items.append(OFFLINE_NOTICE)
    return items
