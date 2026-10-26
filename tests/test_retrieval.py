"""知识检索测试（P6 / P7）。"""

from __future__ import annotations

import json
from pathlib import Path

from contracts import Slots
from tools.medical_search import (
    KB_PATH,
    KnowledgeBase,
    get_knowledge_base,
    load_knowledge,
    search,
)

CASES_PATH = Path(__file__).with_name("cases.json")


def test_knowledge_loads() -> None:
    entries = load_knowledge()
    assert len(entries) >= 10
    assert all(entry["id"] for entry in entries)


def test_all_verified_urls_are_http() -> None:
    for entry in load_knowledge():
        if entry["status"] == "verified":
            assert str(entry["source_url"]).startswith("http"), entry["id"]


def test_search_returns_content_with_source() -> None:
    hits = search("发烧三天了", Slots(chief_complaint="发热"))
    assert hits, "发热应能检索到条目"
    top = hits[0]
    assert top.title and top.url.startswith("http") and top.org
    assert top.score > 0


def test_empty_query_returns_empty() -> None:
    assert search("") == []
    assert search("   ") == []


def test_no_match_returns_empty() -> None:
    assert search("量子力学与天体物理", Slots()) == []


def test_low_score_filtered() -> None:
    hits = search("量子力学", Slots(), min_score=0.9)
    assert hits == []


def test_pending_entries_excluded_by_default() -> None:
    entries = load_knowledge()
    pending = [entry for entry in entries if entry["status"] == "pending"]
    if not pending:
        return
    query = pending[0]["title"]
    default_hits = search(query, Slots(), top_k=10)
    assert pending[0]["id"] not in [hit.id for hit in default_hits]
    with_pending = search(query, Slots(), top_k=10, include_pending=True)
    assert pending[0]["id"] in [hit.id for hit in with_pending]


def test_empty_kb_case() -> None:
    """case_17：知识库为空时必须返回空列表而不是报错。"""
    case = next(c for c in json.loads(CASES_PATH.read_text(encoding="utf-8"))["cases"] if c["id"] == "case_17")
    assert case["expect"]["behavior"] == "empty_kb"
    base = KnowledgeBase([])
    assert base.search("发热") == []
    assert base.stats()["total"] == 0


def test_knowledge_file_utf8() -> None:
    payload = json.loads(KB_PATH.read_text(encoding="utf-8"))
    assert payload["entries"]


def test_each_hit_has_matched_terms() -> None:
    hits = search("咳嗽有痰", Slots(chief_complaint="咳嗽"))
    for hit in hits:
        assert hit.matched_terms


def test_slots_topic_boost() -> None:
    base = get_knowledge_base()
    hits = base.search("最近不太舒服", Slots(chief_complaint="腹泻", associated=["脱水"]))
    assert hits and any("腹泻" in hit.title or "腹泻" in " ".join(hit.matched_terms) for hit in hits)
