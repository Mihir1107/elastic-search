"""Stage 7: bulk into a versioned index, then flip the alias.

Never deletes a live index (CONTRIBUTING.md hard rule). Documents land in a concrete
``emails-vN``; the ``emails`` alias is re-pointed only after the document count
and a smoke query both pass, and the swap is a single atomic
``update_aliases`` call so searchers never see a gap.

Idempotent: ``_id`` is the canonical content hash from stage 4, so re-running
upserts the same documents instead of duplicating them.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any

from elasticsearch import Elasticsearch, NotFoundError
from elasticsearch.helpers import parallel_bulk

from ingest.stats import StageStats

_BULK_CHUNK = 50  # small: each doc can carry several 384-dim chunk vectors
_THREADS = 4


def load_mapping(path: Path) -> dict[str, Any]:
    data: dict[str, Any] = json.loads(path.read_text())
    return data


def allowed_fields(mapping: dict[str, Any]) -> set[str]:
    props = mapping.get("mappings", {}).get("properties", {})
    return set(props.keys())


def create_index(es: Elasticsearch, index: str, mapping: dict[str, Any]) -> bool:
    """Create ``index`` if absent. Returns True if it was created."""
    if es.indices.exists(index=index):
        return False
    es.indices.create(
        index=index,
        settings=mapping.get("settings", {}),
        mappings=mapping.get("mappings", {}),
    )
    return True


def to_source(doc: dict[str, Any], allowed: set[str]) -> dict[str, Any]:
    source: dict[str, Any] = {}
    for key, value in doc.items():
        if key == "id" or key not in allowed:
            continue
        if value is None or value == "" or value == []:
            continue
        source[key] = value
    return source


def to_actions(
    docs: Iterable[dict[str, Any]], index: str, allowed: set[str]
) -> Iterator[dict[str, Any]]:
    for doc in docs:
        yield {
            "_index": index,
            "_id": str(doc["id"]),
            "_source": to_source(doc, allowed),
        }


def bulk_index(
    es: Elasticsearch,
    index: str,
    docs: Iterable[dict[str, Any]],
    allowed: set[str],
    stats: StageStats,
) -> None:
    """Bulk with refresh disabled for throughput, restoring the setting afterwards."""
    es.indices.put_settings(index=index, settings={"index": {"refresh_interval": "-1"}})
    try:
        for success, info in parallel_bulk(
            es,
            to_actions(docs, index, allowed),
            thread_count=_THREADS,
            chunk_size=_BULK_CHUNK,
            raise_on_error=False,
            raise_on_exception=False,
        ):
            if success:
                stats.ok()
            else:
                action = next(iter(info.values())) if isinstance(info, dict) else {}
                reason = "unknown"
                if isinstance(action, dict):
                    error = action.get("error")
                    if isinstance(error, dict):
                        reason = str(error.get("type", "unknown"))
                stats.fail(f"bulk:{reason}")
    finally:
        es.indices.put_settings(index=index, settings={"index": {"refresh_interval": "1s"}})
        es.indices.refresh(index=index)


def verify(es: Elasticsearch, index: str, expected: int) -> dict[str, Any]:
    """Count + smoke queries that must pass before the alias is moved."""
    count = int(es.count(index=index)["count"])
    sample = es.search(index=index, query={"match_all": {}}, size=1)
    with_vectors = es.search(
        index=index,
        size=0,
        query={
            "nested": {
                "path": "chunks",
                "query": {"exists": {"field": "chunks.vector"}},
            }
        },
    )
    vector_docs = int(with_vectors["hits"]["total"]["value"])
    sample_hits = int(sample["hits"]["total"]["value"])
    return {
        "count": count,
        "expected": expected,
        "count_ok": count == expected,
        "sample_hits": sample_hits,
        "docs_with_vectors": vector_docs,
        "smoke_ok": sample_hits > 0 and vector_docs > 0,
    }


def flip_alias(es: Elasticsearch, alias: str, index: str) -> list[str]:
    """Point ``alias`` at ``index`` atomically; returns indices detached."""
    actions: list[dict[str, Any]] = [{"add": {"index": index, "alias": alias}}]
    detached: list[str] = []
    try:
        current = es.indices.get_alias(name=alias)
        for other in current:
            if other != index:
                actions.append({"remove": {"index": other, "alias": alias}})
                detached.append(other)
    except NotFoundError:
        pass
    es.indices.update_aliases(actions=actions)
    return detached


def run(
    es: Elasticsearch,
    in_path: Path,
    mapping_path: Path,
    index: str,
    alias: str,
) -> StageStats:
    from ingest.jsonl import count_lines, read_jsonl

    stats = StageStats("index")
    mapping = load_mapping(mapping_path)
    allowed = allowed_fields(mapping)

    created = create_index(es, index, mapping)
    stats.extra["index"] = index
    stats.extra["index_created"] = created

    expected = count_lines(in_path)
    bulk_index(es, index, read_jsonl(in_path), allowed, stats)

    report = verify(es, index, expected)
    stats.extra["verify"] = report

    if report["count_ok"] and report["smoke_ok"]:
        detached = flip_alias(es, alias, index)
        stats.extra["alias"] = alias
        stats.extra["alias_flipped"] = True
        stats.extra["alias_detached_from"] = detached
    else:
        stats.extra["alias_flipped"] = False
        stats.fail("verification-failed")

    return stats
