"""Stage 5: assign ``thread_id``.

Primary signal is the RFC-822 reply graph (Message-ID / In-Reply-To /
References), unioned with a disjoint-set structure so a whole reply chain
collapses to one root. Messages the header graph leaves unconnected fall back
to a subject heuristic, which on this corpus does all the work (the CALO
release carries no reply headers). A message joins an earlier one only when

* its own subject is a reply or forward (a Re:/Fw: prefix) of the same
  normalised subject -- two unprefixed messages with one subject are separate
  sends, not a conversation;
* it answers that message: its sender received it, or it is addressed to that
  message's sender -- merely sharing someone is not enough;
* and it falls within the time window of that message.

The first two rules are DECISIONS D36. Before them, "any shared participant"
chained every hourly "Schedule Crawler: HourAhead Failure" alert into one
343-message thread, a weekly newsletter into 44 messages over nine months, and
one person's replies to 18 separate congratulations into a single thread.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from ingest.parse import is_forward, is_reply_or_forward, normalise_subject
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


def _recipients(doc: dict[str, Any]) -> set[str]:
    addresses = [*(doc.get("to") or []), *(doc.get("cc") or []), *(doc.get("bcc") or [])]
    return {str(a) for a in addresses if a}


def _answer_strength(reply: dict[str, Any], earlier: dict[str, Any]) -> int:
    """How plausibly ``reply`` continues ``earlier``: 2 strong, 1 weak, 0 not at all.

    Strong: it is addressed to the sender of ``earlier`` -- a reply goes back to
    whoever wrote. Weak: its sender received ``earlier`` (a reply-all, or the
    reply went to someone else on the thread), or it is the same sender following
    up with the same people or forwarding their own message on. Two messages
    that merely share a participant -- one person replying to two different
    people -- are neither.
    """
    sender, earlier_sender = str(reply.get("from") or ""), str(earlier.get("from") or "")
    recipients, earlier_recipients = _recipients(reply), _recipients(earlier)
    if earlier_sender and earlier_sender in recipients and sender != earlier_sender:
        return 2
    if sender and sender in earlier_recipients:
        return 1
    if sender and sender == earlier_sender:
        same_people = bool(recipients & earlier_recipients)
        return 1 if same_people or is_forward(str(reply.get("subject") or "")) else 0
    return 0


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
        for i, curr in enumerate(ordered):
            if not is_reply_or_forward(str(curr.get("subject") or "")):
                continue
            when = _parse_iso(curr.get("date"))
            # The most recent earlier message this one answers most strongly,
            # inside the window: a direct reply to its author beats anything else.
            best: dict[str, Any] | None = None
            best_strength = 0
            for prev in reversed(ordered[:i]):
                then = _parse_iso(prev.get("date"))
                if when and then and (when - then).total_seconds() > window:
                    break
                strength = _answer_strength(curr, prev)
                if strength > best_strength:
                    best, best_strength = prev, strength
                    if strength == 2:
                        break
            if best is not None and dsu.find(str(best["id"])) != dsu.find(str(curr["id"])):
                dsu.union(str(best["id"]), str(curr["id"]))
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
