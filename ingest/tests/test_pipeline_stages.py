"""Unit tests for normalise / dedupe / thread / chunking (no Elasticsearch)."""

from __future__ import annotations

from typing import Any

from ingest.dedupe import canonical_id, dedupe
from ingest.embed import chunk_text, embeddable_text
from ingest.normalise import dedupe_preserve_order, normalise_address, normalise_doc
from ingest.stats import StageStats
from ingest.thread import DisjointSet, assign_threads


def _doc(**kw: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "from": "a@enron.com",
        "to": ["b@enron.com"],
        "cc": [],
        "bcc": [],
        "subject": "Deal",
        "body": "Body text",
        "date": "2001-05-14T23:39:00+00:00",
        "message_id": "",
        "in_reply_to": "",
        "references": [],
        "mailbox": "allen-p",
        "folder": "inbox",
        "source_path": "allen-p/inbox/1.",
    }
    base.update(kw)
    return base


# --------------------------- normalise ---------------------------


def test_normalise_address_lowercases_and_strips_brackets() -> None:
    assert normalise_address("  <Jeff.Skilling@ENRON.com> ") == "jeff.skilling@enron.com"


def test_dedupe_preserve_order_keeps_first_occurrence() -> None:
    assert dedupe_preserve_order(["b", "a", "b", "c", ""]) == ["b", "a", "c"]


def test_normalise_doc_lowercases_recipients_and_sets_person_id() -> None:
    out = normalise_doc(
        _doc(
            **{
                "from": "Phillip.Allen@ENRON.com",
                "to": ["Tim.Belden@enron.com", "TIM.BELDEN@enron.com"],
                "cc": ["Ken.Lay@Enron.com"],
            }
        )
    )
    assert out["from"] == "phillip.allen@enron.com"
    assert out["to"] == ["tim.belden@enron.com"]  # duplicate collapsed
    assert out["cc"] == ["ken.lay@enron.com"]
    assert out["person_id"] == "phillip.allen@enron.com"


# --------------------------- dedupe ---------------------------


def test_canonical_id_is_stable_and_content_addressed() -> None:
    a = canonical_id(_doc())
    b = canonical_id(_doc(mailbox="belden-t", source_path="belden-t/inbox/9."))
    assert a == b, "mailbox location must not change the canonical id"
    assert canonical_id(_doc(body="different")) != a


def test_same_message_in_two_mailboxes_merges_into_one_doc() -> None:
    stats = StageStats("dedupe")
    docs = [
        _doc(mailbox="allen-p", folder="sent", source_path="allen-p/sent/1."),
        _doc(mailbox="belden-t", folder="inbox", source_path="belden-t/inbox/7."),
    ]
    merged = dedupe(docs, stats)

    assert len(merged) == 1
    assert sorted(merged[0]["mailboxes"]) == ["allen-p", "belden-t"]
    assert sorted(merged[0]["folder"]) == ["inbox", "sent"]
    assert merged[0]["duplicate_count"] == 2
    assert stats.skip_reasons["duplicate-merged"] == 1


# --------------------------- thread ---------------------------


def test_disjoint_set_unions_are_deterministic() -> None:
    d1, d2 = DisjointSet(), DisjointSet()
    d1.union("b", "a")
    d2.union("a", "b")
    assert d1.find("a") == d2.find("b") == "a"


def test_reply_headers_group_a_thread() -> None:
    stats = StageStats("thread")
    root = _doc(message_id="root@enron.com", subject="Raptor")
    root["id"] = "id-root"
    reply = _doc(
        message_id="reply@enron.com",
        in_reply_to="root@enron.com",
        subject="Re: Raptor",
        body="reply body",
    )
    reply["id"] = "id-reply"
    other = _doc(message_id="x@enron.com", subject="Lunch", body="unrelated")
    other["id"] = "id-other"

    out = assign_threads([root, reply, other], stats)
    by_id = {d["id"]: d for d in out}
    assert by_id["id-root"]["thread_id"] == by_id["id-reply"]["thread_id"]
    assert by_id["id-other"]["thread_id"] != by_id["id-root"]["thread_id"]
    assert stats.extra["linked_by_headers"] >= 1


def test_subject_fallback_groups_when_headers_are_missing() -> None:
    stats = StageStats("thread")
    a = _doc(subject="Budget review", body="one", date="2001-05-14T10:00:00+00:00")
    a["id"] = "id-a"
    b = _doc(subject="Re: Budget review", body="two", date="2001-05-16T10:00:00+00:00")
    b["id"] = "id-b"

    out = assign_threads([a, b], stats)
    assert out[0]["thread_id"] == out[1]["thread_id"]
    assert stats.extra["linked_by_subject_fallback"] >= 1


def test_subject_fallback_respects_the_time_window() -> None:
    stats = StageStats("thread")
    a = _doc(subject="Budget review", body="one", date="2001-01-01T10:00:00+00:00")
    a["id"] = "id-a"
    b = _doc(subject="Re: Budget review", body="two", date="2001-12-01T10:00:00+00:00")
    b["id"] = "id-b"

    out = assign_threads([a, b], stats, window_days=30)
    assert out[0]["thread_id"] != out[1]["thread_id"]


# --------------------------- chunking ---------------------------


class _FakeTokenizer:
    def __init__(self) -> None:
        self._words: list[str] = []

    def encode(self, text: str, add_special_tokens: bool = False) -> list[int]:
        self._words = text.split()
        return list(range(len(self._words)))

    def decode(self, ids: list[int], skip_special_tokens: bool = True) -> str:
        return " ".join(self._words[i] for i in ids)


class _FakeModel:
    def __init__(self) -> None:
        self.tokenizer = _FakeTokenizer()


def test_chunk_text_windows_with_overlap() -> None:
    model = _FakeModel()
    text = " ".join(f"w{i}" for i in range(25))
    chunks = chunk_text(model, text, chunk_size=10, overlap=2, max_chunks=8)  # type: ignore[arg-type]

    assert len(chunks) == 3
    assert chunks[0].split()[0] == "w0"
    # stride = 10 - 2 = 8, so the second window starts at w8 (overlap preserved)
    assert chunks[1].split()[0] == "w8"


def test_chunk_text_respects_max_chunks() -> None:
    model = _FakeModel()
    text = " ".join(f"w{i}" for i in range(500))
    chunks = chunk_text(model, text, chunk_size=10, overlap=0, max_chunks=3)  # type: ignore[arg-type]
    assert len(chunks) == 3


def test_chunk_text_empty_input_returns_no_chunks() -> None:
    model = _FakeModel()
    assert chunk_text(model, "   ", 10, 2, 8) == []  # type: ignore[arg-type]


def test_embeddable_text_combines_subject_and_body() -> None:
    assert embeddable_text({"subject": "S", "body": "B"}) == "S\n\nB"
    assert embeddable_text({"subject": "S", "body": ""}) == "S"
    assert embeddable_text({"subject": "", "body": "B"}) == "B"
