"""离线模式测试（P10）：必须显性标注，不得伪装成模型输出。"""

from __future__ import annotations

from agent import offline
from agent.controller import AgentController
from agent.llm import Config
from contracts import SLOT_QUESTIONS, RiskLevel, Slots, TriageResult
from tools.triage_rules import screen

REQUIRED_KEYS = {
    "chief_complaint",
    "collected",
    "missing",
    "risk",
    "next_steps",
    "knowledge_summary",
    "red_flags_to_watch",
    "limitations",
}


def _triage(text: str) -> TriageResult:
    from agent.controller import extract_slots

    return screen(text, extract_slots(text))


def test_report_schema_complete() -> None:
    text = "咳嗽三天，有点痰，5 分"
    report = offline.build_report(Slots(), _triage(text), [])
    assert REQUIRED_KEYS <= set(report)
    assert set(report["collected"]) == {"duration", "severity", "associated", "background"}
    assert report["risk"]["level"] in {level.value for level in RiskLevel}


def test_report_marks_offline() -> None:
    report = offline.build_report(Slots(), _triage("发烧 39.5 度两天了"), [])
    assert any("未调用大语言模型" in item for item in report["limitations"])


def test_report_without_knowledge_is_explicit() -> None:
    report = offline.build_report(Slots(), _triage("咳嗽三天，有点痰，5 分"), [])
    assert report["knowledge_summary"] == []
    assert any("未检索到可靠知识条目" in item for item in report["limitations"])


def test_ask_variants_rotate() -> None:
    first = offline.render_ask(["duration"], 0)
    second = offline.render_ask(["duration"], 1)
    third = offline.render_ask(["duration"], 2)
    assert first and second and third
    assert len({first, second, third}) == 3, "同一槽位必须准备多种问法"


def test_ask_matches_slot_templates() -> None:
    for slot, variants in SLOT_QUESTIONS.items():
        for style in ("direct", "choice", "reason"):
            assert variants[style].strip(), (slot, style)


def test_emergency_text_contains_120() -> None:
    triage = _triage("胸口压着疼，一直出汗，二十分钟了")
    text = offline.render_emergency(triage)
    assert "120" in text
    assert "诊断" in text, "必须带免责说明"


def test_offline_controller_greeting_flags_mode() -> None:
    controller = AgentController(config=Config(api_key=""))
    greeting = controller.greeting()
    assert "离线" in greeting
    assert "不做诊断" in greeting


def test_next_steps_per_level() -> None:
    for text in ("胸口压着疼，出汗", "发烧 39.5 度两天了", "咳嗽三天，有点痰，5 分", "不舒服"):
        triage = _triage(text)
        report = offline.build_report(Slots(), triage, [])
        assert report["next_steps"], text
        assert len(report["next_steps"]) <= 6
