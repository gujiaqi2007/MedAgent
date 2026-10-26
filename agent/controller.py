"""Agent 控制流程（BASELINE.md §9）。

关键约束：
* 是否追问由确定性槽位引擎决定，模型只负责措辞（P1）；
* EMERGENCY 一律短路，不等待检索、不等待模型（P2/P8）；
* 任何模型异常都降级到离线模板，绝不把异常抛给前端（P18）。
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass
from typing import Any, Callable

from agent import llm, offline, prompts
from contracts import (
    MAX_ASK_ROUNDS,
    SLOT_LABELS,
    KnowledgeHit,
    Mode,
    Reply,
    RiskLevel,
    Session,
    Slots,
    SourceTag,
    TriageResult,
    Turn,
)
from tools import medical_search
from tools.triage_rules import screen

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# 槽位抽取（规则优先，模型只做补充；见 §8.3）
# --------------------------------------------------------------------------- #
SYMPTOM_TERMS = [
    "胸痛", "胸闷", "心悸", "心慌", "呼吸困难", "喘不上气", "咳嗽", "咳痰", "发热", "发烧",
    "头痛", "头晕", "恶心", "呕吐", "腹泻", "拉肚子", "腹痛", "肚子痛", "皮疹", "瘙痒",
    "咽痛", "流涕", "鼻塞", "乏力", "水肿", "麻木", "腰痛", "关节痛", "失眠", "出血", "不舒服",
]

ASSOCIATED_MAP: dict[str, str] = {
    "发热": "发热", "发烧": "发热", "低烧": "发热", "高烧": "发热", "体温高": "发热",
    "寒战": "寒战", "咳嗽": "咳嗽", "咳痰": "咳痰", "痰": "咳痰",
    "咽痛": "咽痛", "喉咙痛": "咽痛", "流涕": "流涕", "鼻塞": "鼻塞",
    "头痛": "头痛", "头疼": "头痛", "头晕": "头晕", "眩晕": "头晕",
    "恶心": "恶心", "呕吐": "呕吐", "腹泻": "腹泻", "拉肚子": "腹泻",
    "便秘": "便秘", "腹痛": "腹痛", "肚子痛": "腹痛", "胸痛": "胸痛", "胸闷": "胸闷",
    "心慌": "心悸", "心悸": "心悸", "气短": "气短", "喘": "气短",
    "乏力": "乏力", "没力气": "乏力", "皮疹": "皮疹", "起包": "皮疹", "风团": "皮疹",
    "瘙痒": "瘙痒", "水肿": "水肿", "麻木": "麻木", "视物模糊": "视物模糊",
    "失眠": "失眠", "出血": "出血", "出汗": "出汗",
}

CHRONIC_TERMS = [
    "高血压", "糖尿病", "冠心病", "心脏病", "哮喘", "慢性肾病", "肾病", "肝病",
    "肿瘤", "癌症", "中风", "脑梗", "慢阻肺", "甲亢", "甲减", "贫血",
]

IMMUNO_TERMS = ["化疗", "放疗", "免疫抑制剂", "器官移植", "白细胞低", "免疫力低", "免疫缺陷", "长期激素"]

NEGATORS = ("没有", "没", "无", "不", "未", "否认", "并没有", "从来没有")
NEGATOR_EXCEPTIONS = ("不仅", "不但", "不停", "不断", "不舒服", "不想")

SEVERITY_WORDS: list[tuple[str, int]] = [
    ("无法忍受", 10),
    ("痛得打滚", 10),
    ("受不了", 9),
    ("剧烈", 8),
    ("非常严重", 8),
    ("很严重", 8),
    ("严重", 7),
    ("难受得厉害", 7),
    ("中等", 5),
    ("一般", 4),
    ("还好", 4),
    ("有点", 3),
    ("轻微", 3),
    ("隐隐", 3),
    ("不严重", 2),
]

DURATION_RE = re.compile(r"(\d+|[一二两三四五六七八九十]+|半)\s*(分钟|小时|天|日|周|星期|个月|月|年)")
AGE_RE = re.compile(r"(\d{1,3})\s*岁")
INFANT_AGE_RE = re.compile(r"(宝宝|婴儿|新生儿|小孩|孩子|娃|女儿|儿子)[^。！？]{0,10}?(\d{1,2})\s*个月")
INFANT_AGE_RE2 = re.compile(r"(\d{1,2})\s*个月\s*(大|的)")
SEVERITY_NUM_RE = re.compile(r"(\d{1,2})\s*分(?!钟)")


def _negated_at(text: str, index: int) -> bool:
    window = text[max(0, index - 6) : index]
    if any(exception in window for exception in NEGATOR_EXCEPTIONS):
        return False
    return any(negator in window for negator in NEGATORS)


def _first_occurrence(text: str, terms: list[str]) -> tuple[str, int] | None:
    """返回最早出现的未被否定的词及其位置。"""
    best: tuple[str, int] | None = None
    for term in terms:
        start = 0
        while True:
            index = text.find(term, start)
            if index < 0:
                break
            if not _negated_at(text, index):
                if best is None or index < best[1]:
                    best = (term, index)
                break
            start = index + len(term)
    return best


def extract_slots(text: str) -> Slots:
    """从单轮用户输入中抽取槽位。只做保守抽取，不推断。"""
    slots = Slots()
    if not text:
        return slots

    # --- 年龄段（先做，避免 "8 个月" 被当成持续时间） -----------------------
    infant_span: tuple[int, int] | None = None
    if "新生儿" in text:
        slots.age_group = "infant"
    for pattern in (INFANT_AGE_RE, INFANT_AGE_RE2):
        match = pattern.search(text)
        if match:
            slots.age_group = "infant"
            infant_span = match.span()
            break

    age_match = AGE_RE.search(text)
    if age_match and not infant_span:
        age = int(age_match.group(1))
        if age <= 1:
            slots.age_group = "infant"
        elif age < 14:
            slots.age_group = "child"
        elif age >= 65:
            slots.age_group = "elderly"
        else:
            slots.age_group = "adult"

    if not slots.age_group:
        if any(word in text for word in ("婴儿", "宝宝", "娃")):
            slots.age_group = "infant"
        elif any(word in text for word in ("孩子", "小孩", "儿童", "小朋友")):
            slots.age_group = "child"
        elif any(word in text for word in ("老人", "老年", "爷爷", "奶奶", "外公", "外婆")):
            slots.age_group = "elderly"

    # --- 持续时间 --------------------------------------------------------- #
    excluded: list[tuple[int, int]] = []
    if infant_span:
        excluded.append(infant_span)
    pregnancy = re.search(r"孕\s*\d+\s*周|怀孕\s*\d+\s*周|(\d{1,2})\s*孕周", text)
    if pregnancy:
        excluded.append(pregnancy.span())

    for match in DURATION_RE.finditer(text):
        if any(not (match.end() <= start or match.start() >= end) for start, end in excluded):
            continue  # 与月龄/孕周重叠，跳过
        slots.duration = match.group(0).strip()
        break

    # --- 严重程度 --------------------------------------------------------- #
    num_match = SEVERITY_NUM_RE.search(text)
    if num_match:
        value = int(num_match.group(1))
        if 0 <= value <= 10:
            slots.severity = value
    if slots.severity is None:
        for word, value in SEVERITY_WORDS:
            if word in text and not _negated_at(text, text.find(word)):
                slots.severity = value
                break

    # --- 性别 / 孕产 ------------------------------------------------------ #
    if re.search(r"女|女士|女性|老婆|妻子|女朋友|宝妈|孕妇", text):
        slots.sex = "female"
    elif re.search(r"男|先生|男性|老公|丈夫|男朋友", text):
        slots.sex = "male"

    if re.search(r"怀孕|孕期|孕妇|妊娠|孕\s*\d+\s*周", text):
        if not _negated_at(text, max(0, text.find("怀孕"))):
            slots.pregnant = True
            slots.sex = "female"
    elif re.search(r"没怀孕|没有怀孕|未怀孕|不是孕妇", text):
        slots.pregnant = False

    # --- 伴随症状 --------------------------------------------------------- #
    found: list[str] = []
    for term, canonical in ASSOCIATED_MAP.items():
        index = text.find(term)
        if index >= 0 and not _negated_at(text, index) and canonical not in found:
            found.append(canonical)
    slots.associated = found

    # --- 基础病 / 免疫状态 ------------------------------------------------ #
    slots.chronic = [term for term in CHRONIC_TERMS if term in text and not _negated_at(text, text.find(term))]
    if any(term in text for term in IMMUNO_TERMS):
        slots.immunocompromised = True

    # --- 否定项 ----------------------------------------------------------- #
    negations: list[str] = []
    for term in SYMPTOM_TERMS:
        for pattern in (f"没有{term}", f"没{term}", f"无{term}", f"不{term}", f"否认{term}"):
            if pattern in text:
                negations.append(term)
                break
    slots.negations = list(dict.fromkeys(negations))

    # --- 主诉 ------------------------------------------------------------- #
    first = _first_occurrence(text, SYMPTOM_TERMS)
    if first:
        slots.chief_complaint = first[0]
    elif text.strip():
        slots.chief_complaint = text.strip()[:12]

    return slots


def merge_slots(base: Slots, new: Slots) -> Slots:
    """合并槽位：只填空白，不覆盖用户已明确提供的信息。"""
    merged = Slots(**base.to_dict())
    for field in ("chief_complaint", "duration", "age_group", "sex"):
        if not getattr(merged, field) and getattr(new, field):
            setattr(merged, field, getattr(new, field))
    if merged.severity is None and new.severity is not None:
        merged.severity = new.severity
    if merged.pregnant is None and new.pregnant is not None:
        merged.pregnant = new.pregnant
    if merged.immunocompromised is None and new.immunocompromised is not None:
        merged.immunocompromised = new.immunocompromised
    merged.associated = list(dict.fromkeys(merged.associated + new.associated))
    merged.chronic = list(dict.fromkeys(merged.chronic + new.chronic))
    merged.negations = list(dict.fromkeys(merged.negations + new.negations))
    return merged


# --------------------------------------------------------------------------- #
# 控制器
# --------------------------------------------------------------------------- #
class AgentController:
    """一次会话一个实例。前端只调用 `greeting()` 与 `handle()`。"""

    def __init__(
        self,
        config: llm.Config | None = None,
        client: Any | None = None,
        client_factory: Callable[[llm.Config], Any] | None = None,
        ask_rounds: int = MAX_ASK_ROUNDS,
    ) -> None:
        self.config = config or llm.load_config()
        self.session = Session(mode=self.config.mode.value)
        self.ask_rounds = ask_rounds
        self._client = client
        self._client_factory = client_factory
        self._symptom_text = ""

    # ------------------------------------------------------------------ #
    def greeting(self) -> str:
        banner = (
            "\n\n> ⚠️ 当前为**离线演示模式**：使用本地规则与固定模板，未调用大模型。配置 `LLM_API_KEY` 后自动切换。"
            if self.config.mode is Mode.OFFLINE
            else f"\n\n> 模式：在线（模型 {self.config.model}），风险分级仍由本地规则引擎决定。"
        )
        return (
            "你好，我是 MedAgent——一个健康信息整理与就医导航助手。\n\n"
            "请用一两句话描述你最不舒服的地方，我会追问几个关键信息，然后给一份带来源的结构化报告。\n\n"
            "**我不做诊断、不开药，也不能替代医生。**"
            + banner
        )

    # ------------------------------------------------------------------ #
    def handle(self, text: str) -> Reply:
        text = (text or "").strip()
        if not text:
            return Reply(kind="error", text="请先描述一下你的不适，例如「咳嗽三天，有点痰」。", mode=self.config.mode.value)

        started = time.time()
        self.session.turns.append(Turn(role="user", content=text, tag=SourceTag.USER))
        self._symptom_text = (self._symptom_text + "。" + text).strip("。")

        new_slots = extract_slots(text)
        self.session.slots = merge_slots(self.session.slots, new_slots)

        triage = screen(self._symptom_text, self.session.slots)
        self.session.triage = triage

        # --- 紧急：短路（不检索、不调用模型） ---------------------------- #
        if triage.level is RiskLevel.EMERGENCY:
            report = offline.build_report(self.session.slots, triage, [])
            self.session.hits = []
            self.session.report = report
            self.session.finished = True
            return Reply(
                kind="emergency",
                text=offline.render_emergency(triage),
                triage=triage,
                report=report,
                missing=triage.missing_slots,
                mode=self.config.mode.value,
            )

        # --- 信息不足：先追问（P1） -------------------------------------- #
        if triage.level is not RiskLevel.URGENT and triage.missing_slots and self.session.ask_count < self.ask_rounds:
            question = self._ask_question(triage.missing_slots)
            self.session.ask_count += 1
            return Reply(
                kind="ask",
                text=question,
                triage=triage,
                missing=triage.missing_slots,
                mode=self.config.mode.value,
            )

        # --- 出报告 ------------------------------------------------------ #
        report, mode_used, degraded, note = self._build_report(triage, started)
        self.session.report = report
        self.session.mode = mode_used
        self.session.finished = True
        return Reply(
            kind="report",
            text=self._report_summary(report, triage, degraded, note),
            triage=triage,
            report=report,
            missing=triage.missing_slots,
            mode=mode_used,
            degraded=degraded,
            note=note,
        )

    # ------------------------------------------------------------------ #
    def _ask_question(self, missing: list[str]) -> str:
        base = offline.render_ask(missing, self.session.ask_count)
        if self.config.mode is Mode.OFFLINE:
            return base
        # 在线模式：让模型润色问法，失败就用模板（追问决策仍由槽位决定）
        try:
            client = self._get_client()
            prompt = (
                "你是一个医疗问诊助手，需要用一句自然、简短的中文向用户追问下面的信息。"
                "只输出这一句问题，不要解释，不要给出任何诊断或建议。\n\n"
                f"需要追问的信息：{SLOT_LABELS.get(missing[0], missing[0])}\n"
                f"参考问法：{base}\n"
                f"已收集信息：{json.dumps(self.session.slots.to_dict(), ensure_ascii=False)}"
            )
            content, _log, _rounds = client.run_tool_loop(
                [
                    {"role": "system", "content": "你只负责把追问说得自然，不做诊断。"},
                    {"role": "user", "content": prompt},
                ],
                dispatch=lambda *_: {"error": "no_tool"},
                tools=[],
            )
            polished = (content or "").strip().replace("\n", " ")
            return polished[:120] if polished else base
        except llm.LLMError as exc:
            logger.info("追问润色失败，回退模板：%s", exc)
            return base

    # ------------------------------------------------------------------ #
    def _build_report(self, triage: TriageResult, started: float) -> tuple[dict, str, bool, str]:
        query = self._search_query()
        hits = medical_search.search(query, self.session.slots, top_k=3)
        self.session.hits = hits

        if self.config.mode is Mode.OFFLINE:
            return offline.build_report(self.session.slots, triage, hits), Mode.OFFLINE.value, False, ""

        if time.time() - started > 40:  # 总预算熔断
            degraded = "本轮交互超过 40 秒预算，已改用本地模板生成报告。"
            return offline.build_report(self.session.slots, triage, hits, degraded), Mode.OFFLINE.value, True, degraded

        try:
            client = self._get_client()
            payload = {
                "user_text": self._symptom_text[:600],
                "slots": self.session.slots.to_dict(),
                "triage": triage.to_dict(),
                "hits": [hit.to_dict() for hit in hits],
            }
            content, tool_log, rounds = client.run_tool_loop(
                [
                    {"role": "system", "content": prompts.SYSTEM_PROMPT},
                    {"role": "user", "content": prompts.REPORT_USER_TEMPLATE.format(
                        payload=json.dumps(payload, ensure_ascii=False))},
                ],
                dispatch=self.dispatch,
            )
            logger.info("在线报告生成完成：rounds=%s tools=%s", rounds, len(tool_log))
            data = llm.parse_json_object(content)
            report, _warnings = llm.validate_report(data, triage, hits, self.session.slots)
            return report, Mode.ONLINE.value, False, ""
        except llm.LLMError as exc:
            logger.warning("模型调用失败，降级离线模板：%s", exc)
            note = f"{exc.cn}，已改用本地规则与模板生成报告。"
            return offline.build_report(self.session.slots, triage, hits, note), Mode.OFFLINE.value, True, note
        except Exception as exc:  # pragma: no cover - 兜底
            logger.exception("未预期异常，降级离线模板")
            note = f"生成报告时出现异常（{type(exc).__name__}），已改用本地模板。"
            return offline.build_report(self.session.slots, triage, hits, note), Mode.OFFLINE.value, True, note

    # ------------------------------------------------------------------ #
    def dispatch(self, name: str, args: dict[str, Any]) -> Any:
        """真实执行工具调用（P8）。未知工具返回错误而不是抛异常。"""
        if name == "screen_risk":
            text = str(args.get("text") or self._symptom_text)
            result = screen(text, self.session.slots)
            return result.to_dict()
        if name == "search_knowledge":
            query = str(args.get("query") or self._search_query())
            top_k = int(args.get("top_k") or 3)
            hits = medical_search.search(query, self.session.slots, top_k=min(max(top_k, 1), 5))
            return {"hits": [hit.to_dict() for hit in hits]}
        return {"error": "unknown_tool", "name": name}

    # ------------------------------------------------------------------ #
    def _search_query(self) -> str:
        """只用结构化槽位构造检索词：被否定的症状不会进入检索（P4 延伸）。"""
        parts: list[str] = []
        if self.session.slots.chief_complaint:
            parts.append(self.session.slots.chief_complaint)
        parts.extend(self.session.slots.associated[:4])
        return " ".join(dict.fromkeys(part for part in parts if part))

    def _report_summary(self, report: dict, triage: TriageResult, degraded: bool, note: str) -> str:
        level = triage.level
        lines = [f"{level.icon} **{level.cn}**", "", level.first_sentence]
        if degraded and note:
            lines += ["", f"> {note}"]
        lines += ["", "报告已生成，见下方「评估报告」区域。"]
        return "\n".join(lines)

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        if self._client_factory is not None:
            self._client = self._client_factory(self.config)
            return self._client
        self._client = llm.LLMClient(self.config)
        return self._client

    # ------------------------------------------------------------------ #
    def reset(self) -> None:
        self.session.reset()
        self.session.mode = self.config.mode.value
        self._symptom_text = ""
