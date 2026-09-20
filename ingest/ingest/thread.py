"""Stage 5: assign ``thread_id``.

Primary signal is the RFC-822 reply graph (Message-ID / In-Reply-To /
References), unioned with a disjoint-set structure so a whole reply chain
collapses to one root. Messages that the header graph leaves isolated fall back
to a normalised-subject heuristic: same subject with Re:/Fw: stripped, at least
one shared participant, and within a bounded time window.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from itertools import pairwise
from pathlib import Path
from typing import Any

from ingest.parse import normalise_subject
from ingest.stats import StageStats


class DisjointSet:
    def __init__(self) -> None:
        self._parent: dict[str, str] = {}

    def add(self, item: str) -> None:
        self._parent.setdefault(item, item)

    def find(self, item: str) -> str:
        self.add(item)
        root = item
        while self._parent[root] != root:
            root = self._parent[root]
        while self._parent[item] != root:  # path compression
            self._parent[item], item = root, self._parent[item]
        return root

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            # Deterministic root choice keeps thread_id stable across runs.
            lo, hi = sorted((ra, rb))
            self._parent[hi] = lo


def _participants(doc: dict[str, Any]) -> set[str]:
    return {
        str(a)
        for a in [
            doc.get("from") or "",
            *(doc.get("to") or []),
            *(doc.get("cc") or []),
            *(doc.get("bcc") or []),
        ]
        if a
    }


def _parse_iso(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


def assign_threads(
    docs: list[dict[str, Any]], stats: StageStats, window_days: int = 30
) -> list[dict[str, Any]]:
    dsu = DisjointSet()
    by_message_id: dict[str, str] = {}
    for doc in docs:
        doc_id = str(doc["id"])
        dsu.add(doc_id)
        mid = str(doc.get("message_id") or "")
        if mid:
            by_message_id.setdefault(mid, doc_id)

    linked_by_headers = 0
    for doc in docs:
        doc_id = str(doc["id"])
        refs = [str(doc.get("in_reply_to") or ""), *(doc.get("references") or [])]
        for ref in refs:
            target = by_message_id.get(str(ref))
            if target and target != doc_id:
                dsu.union(doc_id, target)
                linked_by_headers += 1

    # Subject fallback for messages the header graph did not connect.
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for doc in docs:
        subject = normalise_subject(str(doc.get("subject") or ""))
        if subject:
            groups[subject].append(doc)

    window = window_days * 86400
    linked_by_subject = 0
    for group in groups.values():
        if len(group) < 2:
            continue
        ordered = sorted(group, key=lambda d: str(d.get("date") or ""))
        for prev, curr in pairwise(ordered):
            if dsu.find(str(prev["id"])) == dsu.find(str(curr["id"])):
                continue
            if not (_participants(prev) & _participants(curr)):
                continue
            d1, d2 = _parse_iso(prev.get("date")), _parse_iso(curr.get("date"))
            if d1 is not None and d2 is not None and abs((d2 - d1).total_seconds()) > window:
                continue
            dsu.union(str(prev["id"]), str(curr["id"]))
            linked_by_subject += 1

    sizes: dict[str, int] = defaultdict(int)
    for doc in docs:
        thread_id = dsu.find(str(doc["id"]))
        doc["thread_id"] = thread_id
        sizes[thread_id] += 1
        stats.ok()

    stats.extra["linked_by_headers"] = linked_by_headers
    stats.extra["linked_by_subject_fallback"] = linked_by_subject
    stats.extra["threads"] = len(sizes)
    stats.extra["multi_message_threads"] = sum(1 for n in sizes.values() if n > 1)
    stats.extra["largest_thread"] = max(sizes.values()) if sizes else 0
    return docs


def run(in_path: Path, out_path: Path, window_days: int = 30) -> StageStats:
    from ingest.jsonl import read_jsonl, write_jsonl

    stats = StageStats("thread")
    docs = list(read_jsonl(in_path))
    docs = assign_threads(docs, stats, window_days=window_days)
    stats.extra["written"] = write_jsonl(out_path, docs)
    stats.extra["output"] = str(out_path)
    return stats
