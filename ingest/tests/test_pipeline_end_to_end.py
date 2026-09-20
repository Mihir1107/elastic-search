"""End-to-end pipeline test on a synthetic maildir.

Runs parse -> normalise -> dedupe -> thread -> embed -> index against a real
Elasticsearch, using throwaway paths, a throwaway index and a throwaway alias so
the live ``emails`` alias and ``emails-v1`` are never touched.

Marked ``integration``: needs Elasticsearch and loads the embedding model.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from ingest import dedupe as dedupe_stage
from ingest import embed as embed_stage
from ingest import index as index_stage
from ingest import normalise as normalise_stage
from ingest import parse as parse_stage
from ingest import thread as thread_stage
from ingest.config import IngestSettings, get_settings
from ingest.jsonl import read_jsonl

pytestmark = pytest.mark.integration


def _msg(
    message_id: str,
    subject: str,
    body: str,
    sender: str = "phillip.allen@enron.com",
    to: str = "tim.belden@enron.com",
    in_reply_to: str = "",
    date: str = "Mon, 14 May 2001 16:39:00 -0700 (PDT)",
) -> str:
    reply = f"In-Reply-To: <{in_reply_to}>\n" if in_reply_to else ""
    return (
        f"Message-ID: <{message_id}>\n"
        f"Date: {date}\n"
        f"From: {sender}\n"
        f"To: {to}\n"
        f"Cc: jeff.skilling@ENRON.com\n"
        f"{reply}"
        f"Subject: {subject}\n"
        f"X-From: Phillip K Allen\n\n"
        f"{body}\n"
    )


@pytest.fixture
def maildir(tmp_path: Path) -> Path:
    root = tmp_path / "raw" / "maildir"

    def write(rel: str, content: str) -> None:
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    thread_root = _msg("root@enron.com", "Raptor structure", "Initial read on Raptor.")
    thread_reply = _msg(
        "reply@enron.com",
        "Re: Raptor structure",
        "Agreed, lets discuss the hedge.",
        sender="tim.belden@enron.com",
        to="phillip.allen@enron.com",
        in_reply_to="root@enron.com",
    )
    standalone = _msg("lunch@enron.com", "Lunch", "Lunch at noon downstairs.")

    # Same message in two mailboxes -> must dedupe to one document.
    write("allen-p/sent/1.", thread_root)
    write("belden-t/inbox/1.", thread_root)
    write("belden-t/sent/2.", thread_reply)
    write("allen-p/inbox/2.", thread_reply)
    write("allen-p/inbox/3.", standalone)
    return root


@pytest.fixture
def es_client() -> Iterator[Any]:
    from ingest.es import make_client

    client = make_client(get_settings())
    try:
        if not client.ping():
            pytest.skip("Elasticsearch is not reachable")
        yield client
    finally:
        client.close()


def test_full_pipeline_dedupes_threads_embeds_and_indexes(
    maildir: Path, tmp_path: Path, es_client: Any
) -> None:
    base = get_settings()
    settings = IngestSettings(
        data_dir=tmp_path,
        embed_model=base.embed_model,
        chunk_tokens=64,
        chunk_overlap=8,
        max_chunks=2,
    )
    suffix = uuid.uuid4().hex[:8]
    index_name = f"emails-test-{suffix}"
    alias_name = f"emails-test-alias-{suffix}"

    try:
        parsed = parse_stage.run(maildir, settings.parsed_path, "full", 100)
        assert parsed.processed == 5, parsed.summary()

        normalise_stage.run(settings.parsed_path, settings.normalised_path)
        deduped = dedupe_stage.run(settings.normalised_path, settings.deduped_path)
        # 5 files, 2 of which are duplicates of others -> 3 unique documents.
        assert deduped.extra["unique_documents"] == 3
        assert deduped.skip_reasons["duplicate-merged"] == 2

        docs = list(read_jsonl(settings.deduped_path))
        merged = next(d for d in docs if "Initial read" in d["body"])
        assert sorted(merged["mailboxes"]) == ["allen-p", "belden-t"]
        assert merged["duplicate_count"] == 2

        threaded = thread_stage.run(settings.deduped_path, settings.threaded_path)
        threaded_docs = list(read_jsonl(settings.threaded_path))

        def find(fragment: str) -> dict[str, Any]:
            return next(d for d in threaded_docs if fragment in d["body"])

        root = find("Initial read")
        reply = find("Agreed")
        lunch = find("Lunch at noon")
        assert root["thread_id"] == reply["thread_id"], "reply chain must share a thread"
        assert lunch["thread_id"] != root["thread_id"]
        assert threaded.extra["multi_message_threads"] >= 1

        embedded = embed_stage.run(settings.threaded_path, settings.embedded_path, settings)
        assert embedded.processed == 3
        vectors = list(read_jsonl(settings.embedded_path))
        assert all(d["chunks"] for d in vectors)
        assert len(vectors[0]["chunks"][0]["vector"]) == settings.embed_dims

        indexed = index_stage.run(
            es_client,
            settings.embedded_path,
            settings.mappings_path,
            index_name,
            alias_name,
        )
        assert indexed.failed == 0, indexed.fail_reasons
        assert indexed.extra["verify"]["count_ok"] is True
        assert indexed.extra["alias_flipped"] is True

        # The alias resolves and CC survived the whole chain.
        hits = es_client.search(index=alias_name, query={"term": {"cc": "jeff.skilling@enron.com"}})
        assert hits["hits"]["total"]["value"] == 3

        # Re-running index is idempotent: same ids, same count.
        index_stage.run(
            es_client,
            settings.embedded_path,
            settings.mappings_path,
            index_name,
            alias_name,
        )
        assert int(es_client.count(index=index_name)["count"]) == 3
    finally:
        es_client.indices.delete(index=index_name, ignore_unavailable=True)
