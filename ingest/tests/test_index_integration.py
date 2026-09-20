"""Integration tests: real Elasticsearch, real mapping.

Marked ``integration`` -- deselected by ``make test``, run by ``make test-integration``.
Uses a throwaway index name and never touches the live ``emails`` alias or
``emails-v1`` (CLAUDE.md: never delete a live index).
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from typing import Any

import pytest

from ingest.config import get_settings
from ingest.index import bulk_index, create_index, load_mapping, verify
from ingest.stats import StageStats

pytestmark = pytest.mark.integration


def _doc(doc_id: str, **kw: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": doc_id,
        "message_id": f"{doc_id}@enron.com",
        "thread_id": "t-1",
        "from": "Phillip.Allen@ENRON.com",
        "to": ["tim.belden@enron.com"],
        "cc": ["jeff.skilling@enron.com"],
        "subject": "Raptor partnership structure",
        "body": "Here is my read on the Raptor structure.",
        "date": "2001-05-14T23:39:00+00:00",
        "mailboxes": ["allen-p"],
        "folder": ["sent"],
        "has_attachment": False,
        "duplicate_count": 1,
        "chunks": [{"text": "Raptor structure", "vector": [0.1] * 384}],
    }
    base.update(kw)
    return base


@pytest.fixture
def es_client() -> Iterator[Any]:
    from ingest.es import make_client

    settings = get_settings()
    client = make_client(settings)
    try:
        if not client.ping():
            pytest.skip("Elasticsearch is not reachable")
        yield client
    finally:
        client.close()


@pytest.fixture
def temp_index(es_client: Any) -> Iterator[str]:
    name = f"emails-test-{uuid.uuid4().hex[:8]}"
    yield name
    es_client.indices.delete(index=name, ignore_unavailable=True)


def test_mapping_creates_index_and_round_trips_queries(es_client: Any, temp_index: str) -> None:
    settings = get_settings()
    mapping = load_mapping(settings.mappings_path)
    stats = StageStats("index-test")

    assert create_index(es_client, temp_index, mapping) is True

    docs = [
        _doc("a" * 40),
        _doc(
            "b" * 40,
            # A genuinely different email so the term/range queries discriminate.
            **{
                "from": "tim.belden@enron.com",
                "cc": [],
                "subject": "Lunch plans",
                "body": "Lunch at noon",
                "date": "2002-01-05T12:00:00+00:00",
            },
        ),
    ]
    bulk_index(es_client, temp_index, docs, set(mapping["mappings"]["properties"]), stats)
    assert stats.failed == 0, stats.fail_reasons

    report = verify(es_client, temp_index, expected=2)
    assert report["count_ok"] is True
    assert report["smoke_ok"] is True
    assert report["docs_with_vectors"] == 2

    # keyword normalizer: the mixed-case sender is queryable in lowercase
    res = es_client.search(index=temp_index, query={"term": {"from": "phillip.allen@enron.com"}})
    assert res["hits"]["total"]["value"] == 1

    # cc survived ingestion
    res = es_client.search(index=temp_index, query={"term": {"cc": "jeff.skilling@enron.com"}})
    assert res["hits"]["total"]["value"] == 1

    # date range filter works on the stored UTC ISO-8601 value
    res = es_client.search(
        index=temp_index,
        query={"range": {"date": {"gte": "2001-01-01", "lte": "2001-12-31"}}},
    )
    assert res["hits"]["total"]["value"] == 1

    # nested kNN over chunk vectors returns the parent email
    res = es_client.search(
        index=temp_index,
        knn={
            "field": "chunks.vector",
            "query_vector": [0.1] * 384,
            "k": 2,
            "num_candidates": 10,
        },
        size=2,
    )
    assert res["hits"]["total"]["value"] >= 1


def test_index_settings_match_the_documented_shard_topology(
    es_client: Any, temp_index: str
) -> None:
    settings = get_settings()
    mapping = load_mapping(settings.mappings_path)
    create_index(es_client, temp_index, mapping)

    got = es_client.indices.get_settings(index=temp_index)
    index_settings = got[temp_index]["settings"]["index"]
    # 3 primaries + 1 replica: chosen for the 3-node HA topology (DECISIONS D4).
    assert index_settings["number_of_shards"] == "3"
    assert index_settings["number_of_replicas"] == "1"
