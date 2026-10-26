"""轻量医学知识检索（BASELINE.md §7）。

* 默认只用关键词打分，零服务依赖；
* `status=pending` 的条目默认不返回（P7：未核实来源不得进入报告）；
* 低于 min_score 返回空列表，不硬凑（P6）。
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable

from contracts import KnowledgeHit, Slots

logger = logging.getLogger(__name__)

KB_PATH = Path(__file__).resolve().parent.parent / "knowledge" / "medical_knowledge.json"

W_TITLE = 1.0
W_KEYWORD = 0.8
W_TOPIC = 0.6
W_CONTENT = 0.3
NORMALIZER = 1.8  # 把加权和压到 0–1

REQUIRED_FIELDS = ("id", "title", "summary", "content", "org", "source_url")


class KnowledgeBaseError(ValueError):
    """知识库结构错误。"""


@dataclass
class KnowledgeBase:
    entries: list[dict[str, Any]]

    # ------------------------------------------------------------------ #
    def search(
        self,
        query: str,
        slots: Slots | None = None,
        top_k: int = 3,
        min_score: float = 0.30,
        include_pending: bool = False,
    ) -> list[KnowledgeHit]:
        query = (query or "").strip().lower()
        if not query:
            return []

        slots = slots or Slots()
        extra_terms = {t.lower() for t in ([slots.chief_complaint or ""] + list(slots.associated)) if t}
        full_query = (query + " " + " ".join(sorted(extra_terms))).strip()

        scored: list[tuple[float, dict[str, Any], list[str]]] = []
        for entry in self.entries:
            if entry.get("status") == "pending" and not include_pending:
                continue
            score, matched = self._score(entry, full_query)
            if score >= min_score:
                scored.append((score, entry, matched))

        scored.sort(key=lambda item: item[0], reverse=True)
        hits: list[KnowledgeHit] = []
        for score, entry, matched in scored[:top_k]:
            hits.append(
                KnowledgeHit(
                    id=str(entry["id"]),
                    title=str(entry["title"]),
                    summary=str(entry.get("summary", "")),
                    url=str(entry["source_url"]),
                    org=str(entry.get("org", "")),
                    score=round(min(1.0, score / NORMALIZER), 3),
                    matched_terms=matched,
                    link_level=str(entry.get("link_level", "site")),
                )
            )
        return hits

    # ------------------------------------------------------------------ #
    def _score(self, entry: dict[str, Any], query: str) -> tuple[float, list[str]]:
        """只有检索词真的出现在 query 里才计分，避免"库里有这个词"就算命中。"""
        score = 0.0
        matched: list[str] = []

        title = str(entry.get("title", "")).lower()
        body = (str(entry.get("summary", "")) + str(entry.get("content", ""))).lower()

        for keyword in entry.get("keywords", []):
            keyword = str(keyword).lower()
            if not keyword or keyword not in query:
                continue
            score += W_KEYWORD
            matched.append(keyword)
            if keyword in title:
                score += W_TITLE
            if keyword in body:
                score += W_CONTENT

        for topic in entry.get("topics", []):
            topic = str(topic).lower()
            if topic and topic in query:
                score += W_TOPIC
                matched.append(topic)

        return score, list(dict.fromkeys(matched))

    # ------------------------------------------------------------------ #
    def by_id(self, entry_id: str) -> dict[str, Any] | None:
        return next((e for e in self.entries if str(e.get("id")) == entry_id), None)

    def stats(self) -> dict[str, int]:
        verified = sum(1 for e in self.entries if e.get("status") == "verified")
        pending = sum(1 for e in self.entries if e.get("status") == "pending")
        return {"total": len(self.entries), "verified": verified, "pending": pending}


def load_knowledge(path: str | Path | None = None, strict: bool = True) -> list[dict[str, Any]]:
    kb_path = Path(path) if path else KB_PATH
    if not kb_path.exists():
        if strict:
            raise KnowledgeBaseError(f"知识库文件不存在：{kb_path}")
        logger.warning("知识库文件不存在：%s，将以空库运行", kb_path)
        return []

    with kb_path.open("r", encoding="utf-8") as handle:
        raw = json.load(handle)

    entries = raw["entries"] if isinstance(raw, dict) else raw
    problems: list[str] = []
    seen: set[str] = set()

    for entry in entries:
        for field in REQUIRED_FIELDS:
            if not str(entry.get(field, "")).strip():
                problems.append(f"{entry.get('id', '?')}: 缺少 {field}")
        eid = str(entry.get("id", ""))
        if eid in seen:
            problems.append(f"{eid}: id 重复")
        seen.add(eid)
        url = str(entry.get("source_url", ""))
        if not url.startswith("http"):
            problems.append(f"{eid}: source_url 不是 http(s) 链接")
        if entry.get("status") not in {"verified", "pending"}:
            problems.append(f"{eid}: status 必须是 verified / pending")

    if problems and strict:
        raise KnowledgeBaseError("知识库校验失败：\n- " + "\n- ".join(problems))
    for problem in problems:
        logger.warning("知识库条目问题：%s", problem)

    return entries


@lru_cache(maxsize=4)
def _cached_base(path: str | None = None) -> KnowledgeBase:
    return KnowledgeBase(load_knowledge(path, strict=False))


def get_knowledge_base(path: str | Path | None = None) -> KnowledgeBase:
    return _cached_base(str(path) if path else None)


def search(
    query: str,
    slots: Slots | None = None,
    top_k: int = 3,
    min_score: float = 0.30,
    include_pending: bool = False,
    entries: Iterable[dict[str, Any]] | None = None,
) -> list[KnowledgeHit]:
    """模块级检索入口。传 entries 时使用临时知识库（测试用）。"""
    if entries is not None:
        base = KnowledgeBase(list(entries))
    else:
        base = get_knowledge_base()
    return base.search(
        query,
        slots=slots,
        top_k=top_k,
        min_score=min_score,
        include_pending=include_pending,
    )
