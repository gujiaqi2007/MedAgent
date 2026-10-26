"""规则引擎测试（BASELINE.md §13.2 用例 1–16 的规则侧断言）。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent.controller import extract_slots
from contracts import RiskLevel, Slots
from tools.triage_rules import RULES_PATH, load_rules, screen

CASES_PATH = Path(__file__).with_name("cases.json")


@pytest.fixture(scope="module")
def cases() -> list[dict]:
    return json.loads(CASES_PATH.read_text(encoding="utf-8"))["cases"]


def _conversation_cases(cases: list[dict]) -> list[dict]:
    return [c for c in cases if c["expect"].get("behavior") == "conversation"]


# --------------------------------------------------------------------------- #
# 结构与自检
# --------------------------------------------------------------------------- #
def test_rules_load_ok() -> None:
    rules = load_rules()
    assert len(rules) >= 12


def test_rule_ids_unique_and_complete() -> None:
    rules = load_rules()
    ids = [rule["id"] for rule in rules]
    assert len(ids) == len(set(ids))
    for rule in rules:
        assert rule["level"] in {level.value for level in RiskLevel}
        assert rule["keywords"], f"{rule['id']} 缺少 keywords"
        assert rule["sources"], f"{rule['id']} 缺少 sources"
        assert rule["message"].strip()


def test_rules_have_source_refs() -> None:
    rules = load_rules()
    for rule in rules:
        assert all(source.startswith("S-") for source in rule["sources"]), rule["id"]


def test_rules_file_is_utf8_json() -> None:
    payload = json.loads(RULES_PATH.read_text(encoding="utf-8"))
    assert "rules" in payload and payload["version"]


def test_engine_does_not_import_llm() -> None:
    """P2 红线：规则引擎不得依赖模型。"""
    source = (RULES_PATH.parent.parent / "tools" / "triage_rules.py").read_text(encoding="utf-8")
    assert "openai" not in source.lower()
    assert "import agent" not in source


def test_invalid_rules_rejected(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"rules": [{"id": "X1", "level": "high", "keywords": []}]}), encoding="utf-8")
    with pytest.raises(ValueError):
        load_rules(str(bad))


# --------------------------------------------------------------------------- #
# 分级
# --------------------------------------------------------------------------- #
def test_emergency_cases(cases: list[dict]) -> None:
    for case in _conversation_cases(cases):
        expected = case["expect"].get("level")
        if expected != "emergency":
            continue
        text = "。".join(case["turns"])
        result = screen(text, extract_slots(text))
        assert result.level is RiskLevel.EMERGENCY, (case["id"], result.level)
        assert result.red_flag_actions, case["id"]


def test_urgent_cases(cases: list[dict]) -> None:
    for case in _conversation_cases(cases):
        if case["expect"].get("level") != "urgent":
            continue
        text = "。".join(case["turns"])
        result = screen(text, extract_slots(text))
        assert result.level is RiskLevel.URGENT, (case["id"], result.level)


def test_infant_case_applies_modifier(cases: list[dict]) -> None:
    case = next(c for c in cases if c["id"] == "case_10")
    text = case["turns"][0]
    slots = extract_slots(text)
    result = screen(text, slots)
    assert slots.age_group == "infant"
    assert "infant" in result.modifiers_applied


def test_pregnancy_case(cases: list[dict]) -> None:
    case = next(c for c in cases if c["id"] == "case_11")
    text = case["turns"][0]
    slots = extract_slots(text)
    result = screen(text, slots)
    assert slots.pregnant is True
    assert result.level.rank >= RiskLevel.URGENT.rank
    assert "pregnant" in result.modifiers_applied


# --------------------------------------------------------------------------- #
# 否定 / 假设 / 信息不足（P2 / P3 / P4）
# --------------------------------------------------------------------------- #
def test_negation_blocks_red_flag() -> None:
    text = "我没有胸痛，就是有点咳嗽三天了"
    slots = extract_slots(text)
    result = screen(text, slots)
    assert result.level is not RiskLevel.EMERGENCY
    assert "胸痛" in slots.negations


def test_negation_not_triggered_by_bujin() -> None:
    result = screen("不仅胸痛，还一直出汗", Slots(chief_complaint="胸痛"))
    assert result.level is RiskLevel.EMERGENCY


def test_hypothetical_not_escalated() -> None:
    result = screen("如果我胸痛该怎么办？", Slots())
    assert result.level is not RiskLevel.EMERGENCY


def test_past_tense_downgraded() -> None:
    now = screen("现在胸口压着疼，一直在出汗", Slots(duration="十分钟", severity=6))
    past = screen("以前胸口压着疼过一次，后来好了", Slots(duration="一天", severity=2))
    assert now.level.rank > past.level.rank


def test_insufficient_when_slots_missing() -> None:
    result = screen("不舒服", Slots())
    assert result.level is RiskLevel.INSUFFICIENT
    assert result.missing_slots


def test_unknown_text_is_not_auto_low_risk() -> None:
    result = screen("说不上来哪里怪怪的", Slots())
    assert result.level is RiskLevel.INSUFFICIENT


def test_routine_requires_full_slots() -> None:
    text = "咳嗽三天，有点痰"
    result = screen(text, extract_slots(text + "，严重程度 3 分"))
    assert result.level in {RiskLevel.ROUTINE, RiskLevel.INSUFFICIENT}
    assert result.level is not RiskLevel.EMERGENCY


def test_screening_is_pure() -> None:
    text = "发烧 39.5 度两天了"
    first = screen(text, extract_slots(text))
    second = screen(text, extract_slots(text))
    assert first.to_dict() == second.to_dict()


def test_missing_slots_never_default_low_risk() -> None:
    result = screen("头疼", Slots(chief_complaint="头痛"))
    assert result.level is RiskLevel.INSUFFICIENT
