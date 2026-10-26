"""MedAgent 全局数据契约（BASELINE.md §5）。

约定：
1. 所有模块只允许依赖本文件，不允许相互 import 业务实现；
2. 契约冻结后如需变更，必须在 BASELINE.md §5 变更记录追加一行，并通知 A/B/C/D；
3. 本文件零第三方依赖，可被测试、前端、工具同时 import。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

__all__ = [
    "RiskLevel",
    "SourceTag",
    "Mode",
    "REQUIRED_SLOTS",
    "SOFT_SLOTS",
    "MAX_ASK_ROUNDS",
    "MAX_TOOL_ROUNDS",
    "LLM_TIMEOUT",
    "TOTAL_BUDGET",
    "SLOT_LABELS",
    "SLOT_QUESTIONS",
    "Slots",
    "TriageResult",
    "KnowledgeHit",
    "Turn",
    "Session",
    "Reply",
    "slot_filled",
    "missing_slots",
    "highest_level",
]


# --------------------------------------------------------------------------- #
# 枚举
# --------------------------------------------------------------------------- #
class RiskLevel(str, Enum):
    """四态风险分层。默认态不是低风险，而是"无法充分评估"。"""

    EMERGENCY = "emergency"
    URGENT = "urgent"
    ROUTINE = "routine"
    INSUFFICIENT = "insufficient"

    @property
    def rank(self) -> int:
        return _LEVEL_RANK[self.value]

    @property
    def cn(self) -> str:
        return _LEVEL_CN[self.value]

    @property
    def color(self) -> str:
        return _LEVEL_COLOR[self.value]

    @property
    def icon(self) -> str:
        return _LEVEL_ICON[self.value]

    @property
    def first_sentence(self) -> str:
        return _LEVEL_FIRST[self.value]


_LEVEL_RANK = {"insufficient": 0, "routine": 1, "urgent": 2, "emergency": 3}
_LEVEL_CN = {
    "emergency": "紧急（需立即处理）",
    "urgent": "较紧急（建议 24 小时内就医）",
    "routine": "常规（可先观察，必要时择期就诊）",
    "insufficient": "信息不足（无法充分评估）",
}
_LEVEL_COLOR = {
    "emergency": "#d92d20",
    "urgent": "#e8590c",
    "routine": "#1c7ed6",
    "insufficient": "#6b7280",
}
_LEVEL_ICON = {"emergency": "🚨", "urgent": "⚠️", "routine": "ℹ️", "insufficient": "❓"}
_LEVEL_FIRST = {
    "emergency": "你描述的情况中包含需要立即处理的信号，请现在拨打 120 或让家人陪同前往最近医院急诊。",
    "urgent": "建议在 24 小时内前往医院就诊；如果症状明显加重，请直接前往急诊。",
    "routine": "目前未发现规则覆盖的紧急信号，可先居家观察，并留意下方「需警惕的变化」。",
    "insufficient": "目前收集到的信息还不足以判断风险等级——这不等于「没问题」。以下是你还需要补充的信息。",
}


class SourceTag(str, Enum):
    """报告里每条结论的来源标签（P12）。"""

    USER = "user"
    RULE = "rule"
    MODEL = "model"
    KB = "kb"

    @property
    def cn(self) -> str:
        return {
            "user": "[用户提供]",
            "rule": "[规则筛查]",
            "model": "[模型解释]",
            "kb": "[知识库]",
        }[self.value]


class Mode(str, Enum):
    ONLINE = "online"
    OFFLINE = "offline"


# --------------------------------------------------------------------------- #
# 常量（P8 熔断参数）
# --------------------------------------------------------------------------- #
REQUIRED_SLOTS = ("chief_complaint", "duration", "severity")
SOFT_SLOTS = ("associated", "age_group")

MAX_ASK_ROUNDS = 3
MAX_TOOL_ROUNDS = 3
LLM_TIMEOUT = 25
TOTAL_BUDGET = 40
MAX_TOKENS = 1200

SLOT_LABELS = {
    "chief_complaint": "主要症状",
    "duration": "持续时间",
    "severity": "严重程度",
    "associated": "伴随症状",
    "age_group": "年龄段",
    "sex": "性别",
    "pregnant": "孕产情况",
    "chronic": "基础疾病",
    "immunocompromised": "免疫状态",
}

# 每个槽位 3 种问法：direct / choice / reason（避免复读机）
SLOT_QUESTIONS: dict[str, dict[str, str]] = {
    "chief_complaint": {
        "direct": "你最不舒服的是哪里？大概是什么样的感觉（疼、胀、痒、闷）？",
        "choice": "主要是哪一类：疼痛、发热、咳嗽、消化不适、皮疹，还是其他？",
        "reason": "我想先确认最主要的症状，才好判断该看哪一科。",
    },
    "duration": {
        "direct": "这种情况大概持续多久了？",
        "choice": "是几小时内突然出现的，还是已经持续几天了？",
        "reason": "症状持续多久会影响判断，所以想确认一下时间。",
    },
    "severity": {
        "direct": "如果用 0–10 分给自己打分会是几分（0 分没事、10 分最难忍受）？",
        "choice": "现在还能正常活动吗：能正常工作学习、只能躺着、还是疼得动不了？",
        "reason": "严重程度是风险判断的关键，所以想请你打个分。",
    },
    "associated": {
        "direct": "除了这个，还有没有其他不舒服？",
        "choice": "有没有发热、呕吐、呼吸困难、皮疹或明显乏力？都没有也可以直接说没有。",
        "reason": "伴随症状常常决定风险等级，所以想多问一句。",
    },
    "age_group": {
        "direct": "方便说一下年龄吗？",
        "choice": "是儿童、成人，还是 65 岁以上的老人？",
        "reason": "不同年龄段的风险阈值不一样，所以需要确认。",
    },
    "sex": {
        "direct": "方便说下性别吗？",
        "choice": "男性还是女性？",
        "reason": "部分症状需要结合性别判断，尤其是孕产相关情况。",
    },
    "pregnant": {
        "direct": "是否怀孕，或可能处于孕期？",
        "choice": "有怀孕可能吗？大概多少周？",
        "reason": "孕期出现腹痛或出血需要更谨慎，所以想确认。",
    },
    "chronic": {
        "direct": "有没有高血压、糖尿病、心脏病、哮喘等基础疾病？",
        "choice": "有长期在吃的药或确诊的慢性病吗？没有也可以说没有。",
        "reason": "基础病会影响风险判断和就医建议。",
    },
    "immunocompromised": {
        "direct": "近期有没有化疗、放疗，或长期使用激素、免疫抑制剂？",
        "choice": "有没有做过器官移植，或医生说过免疫力偏低？",
        "reason": "免疫力偏低时，同样的症状可能需要更早就医。",
    },
}


# --------------------------------------------------------------------------- #
# 数据结构
# --------------------------------------------------------------------------- #
@dataclass
class Slots:
    """从用户明说内容中抽取的结构化信息。模型不得推断填充。"""

    chief_complaint: str | None = None
    duration: str | None = None
    severity: int | None = None
    associated: list[str] = field(default_factory=list)
    age_group: str | None = None  # infant | child | adult | elderly
    sex: str | None = None  # female | male | unspecified
    pregnant: bool | None = None
    chronic: list[str] = field(default_factory=list)
    immunocompromised: bool | None = None
    negations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "chief_complaint": self.chief_complaint,
            "duration": self.duration,
            "severity": self.severity,
            "associated": list(self.associated),
            "age_group": self.age_group,
            "sex": self.sex,
            "pregnant": self.pregnant,
            "chronic": list(self.chronic),
            "immunocompromised": self.immunocompromised,
            "negations": list(self.negations),
        }


@dataclass
class TriageResult:
    """规则引擎输出。纯函数产出，不含任何模型参与。"""

    level: RiskLevel = RiskLevel.INSUFFICIENT
    matched_rules: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    missing_slots: list[str] = field(default_factory=list)
    modifiers_applied: list[str] = field(default_factory=list)
    red_flag_actions: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    screening_note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "level": self.level.value,
            "matched_rules": self.matched_rules,
            "reasons": self.reasons,
            "missing_slots": self.missing_slots,
            "modifiers_applied": self.modifiers_applied,
            "red_flag_actions": self.red_flag_actions,
            "sources": self.sources,
            "screening_note": self.screening_note,
        }


@dataclass
class KnowledgeHit:
    id: str
    title: str
    summary: str
    url: str
    org: str
    score: float
    matched_terms: list[str] = field(default_factory=list)
    link_level: str = "site"  # direct | site

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "summary": self.summary,
            "url": self.url,
            "org": self.org,
            "score": round(self.score, 3),
            "matched_terms": self.matched_terms,
            "link_level": self.link_level,
        }


@dataclass
class Turn:
    role: str  # user | assistant | system
    content: str
    tag: SourceTag | None = None
    tool_calls: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class Session:
    turns: list[Turn] = field(default_factory=list)
    slots: Slots = field(default_factory=Slots)
    triage: TriageResult | None = None
    hits: list[KnowledgeHit] = field(default_factory=list)
    report: dict[str, Any] | None = None
    mode: str = "offline"
    ask_count: int = 0
    finished: bool = False

    def reset(self) -> None:
        self.turns = []
        self.slots = Slots()
        self.triage = None
        self.hits = []
        self.report = None
        self.ask_count = 0
        self.finished = False


@dataclass
class Reply:
    """一次用户输入之后的返回结构，前端只认这个。"""

    kind: str  # ask | emergency | report | error
    text: str
    triage: TriageResult | None = None
    report: dict[str, Any] | None = None
    missing: list[str] = field(default_factory=list)
    mode: str = "offline"
    degraded: bool = False
    note: str = ""


# --------------------------------------------------------------------------- #
# 工具函数
# --------------------------------------------------------------------------- #
def slot_filled(slots: Slots, name: str) -> bool:
    """槽位是否已填。空字符串、空列表、None 都算未填。"""
    value = getattr(slots, name, None)
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple)):
        return len(value) > 0
    return True


def missing_slots(slots: Slots, include_soft: bool = True) -> list[str]:
    """按追问优先级返回缺失槽位（P3）。"""
    missing = [s for s in REQUIRED_SLOTS if not slot_filled(slots, s)]
    if include_soft and not any(slot_filled(slots, s) for s in SOFT_SLOTS):
        missing.append("associated")
    return missing


def highest_level(levels: list[RiskLevel]) -> RiskLevel:
    if not levels:
        return RiskLevel.INSUFFICIENT
    return max(levels, key=lambda item: item.rank)
