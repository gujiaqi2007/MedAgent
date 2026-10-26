"""前端冒烟测试：用 Streamlit 官方 AppTest 真跑脚本，确保页面不白屏（P18）。"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("streamlit.testing.v1")

from streamlit.testing.v1 import AppTest  # noqa: E402

APP_PATH = Path(__file__).resolve().parents[1] / "app.py"


def _app() -> AppTest:
    return AppTest.from_file(str(APP_PATH), default_timeout=60)


def test_app_boots_without_exception() -> None:
    at = _app().run()
    assert not at.exception
    assert any("MedAgent" in title.value for title in at.title)
    assert len(at.chat_input) == 1


def test_offline_banner_visible() -> None:
    at = _app().run()
    banners = [item.value for item in at.warning]
    assert any("离线演示模式" in banner for banner in banners)


def test_emergency_turn_renders_report() -> None:
    at = _app().run()
    at.chat_input[0].set_value("胸口压着疼，还一直出汗，大概二十分钟了").run()
    assert not at.exception
    assert any("评估报告" in sub.value for sub in at.subheader)
    assert any("120" in item.value for item in at.error)


def test_normal_turn_renders_report() -> None:
    at = _app().run()
    at.chat_input[0].set_value("咳嗽三天，有点痰，5 分，没有发烧").run()
    assert not at.exception
    assert any("评估报告" in sub.value for sub in at.subheader)
