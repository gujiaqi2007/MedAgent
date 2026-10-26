"""控制流程测试（P1 / P2 / P8 / P10 / P18）。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from agent import llm
from agent.controller import AgentController, extract_slots, merge_slots
from contracts import Mode, Reply, RiskLevel, Slots

CASES_PATH = Path(__file__).with_name("cases.json")


class FakeClient:
    """最小可用的假客户端，用于验证降级与报告校验，不触网。"""

    def __init__(self, content: str = "", error: Exception | None = None) -> None:
        self.content = content
        self.error = error
        self.calls: list[dict[str, Any]] = []

    def run_tool_loop(self, messages, dispatch, tools=None):
        if self.error:
            raise self.error
        dispatch("search_knowledge", {"query": "发热", "top_k": 3})
        self.calls.append({"messages": messages, "tools": tools})
        return self.content, [{"name": "search_knowledge"}], 1


def offline_controller() -> AgentController:
    return AgentController(config=llm.Config(api_key=""))


def online_controller(client: FakeClient) -> AgentController:
    config = llm.Config(api_key="sk-test", base_url="http://127.0.0.1:9/v1", model="fake-model")
    return AgentController(config=config, client=client)


# --------------------------------------------------------------------------- #
# 会话行为
# --------------------------------------------------------------------------- #
def test_emergency_short_circuits() -> None:
    controller = offline_controller()
    reply: Reply = controller.handle("胸口压着疼，还一直出汗，大概二十分钟了")
    assert reply.kind == "emergency"
    assert controller.session.triage is not None
    assert controller.session.triage.level is RiskLevel.EMERGENCY
    assert controller.session.ask_count == 0, "紧急情况不得先追问"
    assert controller.session.hits == [], "紧急情况不应等待检索"


def test_emergency_report_has_actions() -> None:
    controller = offline_controller()
    reply = controller.handle("喘不上气，躺下更严重，嘴唇发紫")
    assert reply.report and reply.report["next_steps"]
    assert any("120" in step for step in reply.report["next_steps"])


def test_ask_then_report() -> None:
    controller = offline_controller()
    reply = controller.handle("不舒服")
    assert reply.kind == "ask"
    assert reply.missing

    reply = controller.handle("三天了，大概 5 分")
    assert reply.kind == "ask"
    assert "duration" not in reply.missing, "已回答的槽位不得重复追问"

    reply = controller.handle("没有发烧，就是有点咳嗽")
    assert reply.kind in {"report", "ask"}


def test_ask_round_limit_then_insufficient() -> None:
    controller = offline_controller()
    for _ in range(3):
        reply = controller.handle("不舒服")
        assert reply.kind == "ask"
    reply = controller.handle("还是不舒服")
    assert reply.kind == "report"
    assert reply.report["risk"]["level"] == RiskLevel.INSUFFICIENT.value


def test_urgent_reports_immediately() -> None:
    controller = offline_controller()
    reply = controller.handle("发烧 39.5 度两天了")
    assert reply.kind == "report"
    assert reply.report["risk"]["level"] == "urgent"


def test_empty_input_is_friendly_error() -> None:
    controller = offline_controller()
    reply = controller.handle("   ")
    assert reply.kind == "error"
    assert "描述" in reply.text


def test_reset_clears_everything() -> None:
    controller = offline_controller()
    controller.handle("胸口压着疼，出汗")
    controller.reset()
    assert controller.session.triage is None
    assert controller.session.report is None
    assert controller.session.ask_count == 0
    assert controller.session.turns == []


# --------------------------------------------------------------------------- #
# 降级
# --------------------------------------------------------------------------- #
def test_auth_error_falls_back_to_offline() -> None:
    """case_18：鉴权失败必须降级，不得崩溃。"""
    client = FakeClient(error=llm.LLMError("auth", "invalid key"))
    controller = online_controller(client)
    reply = controller.handle("咳嗽三天，有痰，5 分")
    assert reply.kind == "report"
    assert reply.mode == Mode.OFFLINE.value
    assert reply.degraded is True
    assert "鉴权失败" in reply.note
    assert reply.report is not None


def test_tool_limit_error_falls_back() -> None:
    client = FakeClient(error=llm.LLMError("tool_limit", "too many rounds"))
    controller = online_controller(client)
    reply = controller.handle("咳嗽三天，有痰，5 分")
    assert reply.degraded is True
    assert reply.mode == Mode.OFFLINE.value


# --------------------------------------------------------------------------- #
# 报告校验（P9）
# --------------------------------------------------------------------------- #
GOOD_REPORT = {
    "chief_complaint": "发热",
    "collected": {"duration": "两天", "severity": "6/10", "associated": ["发热"], "background": []},
    "missing": [],
    "risk": {"level": "routine", "basis": ["模型自己的判断"]},
    "next_steps": ["多喝水"],
    "knowledge_summary": [
        {"id": "k001", "title": "发热时可以先做什么", "url": "https://evil.example.com", "one_line": "记录体温"}  # noqa: E501
    ],
    "red_flags_to_watch": ["意识改变"],
    "limitations": ["仅供参考"],
}


def test_report_risk_level_overridden_by_rules() -> None:
    client = FakeClient(content=json.dumps(GOOD_REPORT, ensure_ascii=False))
    controller = online_controller(client)
    reply = controller.handle("发烧 39.5 度两天了")
    assert reply.report["risk"]["level"] == "urgent", "模型写的 routine 必须被规则覆盖"
    assert any("规则" in item for item in reply.report["limitations"])


def test_report_fabricated_knowledge_removed() -> None:
    payload = json.loads(json.dumps(GOOD_REPORT, ensure_ascii=False))
    payload["knowledge_summary"].append({"id": "k999", "title": "编造条目", "url": "https://fake", "one_line": "x"})
    client = FakeClient(content=json.dumps(payload, ensure_ascii=False))
    controller = online_controller(client)
    reply = controller.handle("发烧 39.5 度两天了")
    ids = [item["id"] for item in reply.report["knowledge_summary"]]
    assert "k999" not in ids


def test_report_url_is_always_from_kb() -> None:
    client = FakeClient(content=json.dumps(GOOD_REPORT, ensure_ascii=False))
    controller = online_controller(client)
    reply = controller.handle("发烧 39.5 度两天了")
    for item in reply.report["knowledge_summary"]:
        assert "evil.example.com" not in item["url"]


def test_malformed_json_falls_back() -> None:
    client = FakeClient(content="这不是 JSON")
    controller = online_controller(client)
    reply = controller.handle("咳嗽三天，有痰，5 分")
    assert reply.degraded is True
    assert reply.report is not None


# --------------------------------------------------------------------------- #
# 槽位
# --------------------------------------------------------------------------- #
def test_extract_slots_basic() -> None:
    slots = extract_slots("宝宝 8 个月，发烧 38.2 度")
    assert slots.age_group == "infant"
    assert slots.duration is None, "月龄不得被当成持续时间"


def test_extract_slots_pregnancy_week() -> None:
    slots = extract_slots("怀孕 30 周，有点出血")
    assert slots.pregnant is True
    assert slots.duration is None, "孕周不得被当成持续时间"


def test_merge_slots_does_not_overwrite() -> None:
    base = Slots(duration="三天", severity=5)
    merged = merge_slots(base, Slots(duration="五天", severity=9, chief_complaint="咳嗽"))
    assert merged.duration == "三天"
    assert merged.severity == 5
    assert merged.chief_complaint == "咳嗽"


# --------------------------------------------------------------------------- #
# 全量用例回归
# --------------------------------------------------------------------------- #
def _cases() -> list[dict]:
    return json.loads(CASES_PATH.read_text(encoding="utf-8"))["cases"]


@pytest.mark.parametrize("case", [c for c in _cases() if c["expect"].get("behavior") == "conversation"])
def test_conversation_cases(case: dict) -> None:
    controller = offline_controller()
    for turn in case["turns"]:
        controller.handle(turn)

    triage = controller.session.triage
    assert triage is not None, case["id"]

    expect = case["expect"]
    if "level" in expect:
        assert triage.level.value == expect["level"], (case["id"], triage.level.value, triage.reasons)
    if "level_not" in expect:
        assert triage.level.value != expect["level_not"], (case["id"], triage.level.value)
    for rule_id in expect.get("rules_contain", []):
        assert rule_id in triage.matched_rules, (case["id"], triage.matched_rules)
    for modifier in expect.get("modifiers_contain", []):
        assert modifier in triage.modifiers_applied, (case["id"], triage.modifiers_applied)
    for negation in expect.get("negations_contain", []):
        assert negation in controller.session.slots.negations, case["id"]
