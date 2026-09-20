"""Run retrieval methods over the query set and build candidate pools.

Methods are executed through the real ``run_search`` pipeline, so the evaluation
measures exactly the query construction, filtering and fusion that production
uses rather than a parallel re-implementation that could drift.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

import yaml
from elasticsearch import AsyncElasticsearch

from app.config import Settings
from app.search.service import run_search

METHODS: tuple[str, ...] = ("bm25", "vector", "hybrid", "hybrid+rerank")

#: "<leg>+rerank" runs that leg then the local cross-encoder.
RERANK_SUFFIX = "+rerank"
RUN_DEPTH = 50  # enough for recall@50
POOL_DEPTH = 20  # union of the top 20 of every method


def load_queries(path: Path) -> list[dict[str, Any]]:
    data = yaml.safe_load(path.read_text())
    queries: list[dict[str, Any]] = list(data["queries"])
    return queries


async def run_method(
    es: AsyncElasticsearch,
    settings: Settings,
    query_text: str,
    method: str,
    size: int = RUN_DEPTH,
) -> list[str]:
    leg, rerank = method, False
    if method.endswith(RERANK_SUFFIX):
        leg, rerank = method[: -len(RERANK_SUFFIX)], True
    response = await run_search(
        es,
        settings,
        q=query_text,
        size=size,
        method=leg,  # type: ignore[arg-type]
        rerank=rerank,
    )
    return [hit.id for hit in response.hits]


async def run_all(
    es: AsyncElasticsearch,
    settings: Settings,
    queries: Sequence[dict[str, Any]],
    methods: Sequence[str] = METHODS,
    size: int = RUN_DEPTH,
) -> dict[str, dict[str, list[str]]]:
    """Returns {method: {query_id: [doc_id, ...]}}."""
    runs: dict[str, dict[str, list[str]]] = {m: {} for m in methods}
    for query in queries:
        for method in methods:
            runs[method][str(query["id"])] = await run_method(
                es, settings, str(query["query"]), method, size
            )
    return runs


def build_pools(
    runs: dict[str, dict[str, list[str]]], depth: int = POOL_DEPTH
) -> dict[str, list[str]]:
    """Union of the top ``depth`` documents from every method, per query."""
    pools: dict[str, list[str]] = {}
    for per_query in runs.values():
        for query_id, ranked in per_query.items():
            bucket = pools.setdefault(query_id, [])
            for doc_id in ranked[:depth]:
                if doc_id not in bucket:
                    bucket.append(doc_id)
    return pools


async def fetch_docs(
    es: AsyncElasticsearch, settings: Settings, doc_ids: Sequence[str]
) -> dict[str, dict[str, Any]]:
    """Fetch the fields the grading rules and the labelling CLI need."""
    if not doc_ids:
        return {}
    out: dict[str, dict[str, Any]] = {}
    fields = ["subject", "from", "to", "date", "body"]
    batch = 200
    for start in range(0, len(doc_ids), batch):
        chunk = list(doc_ids[start : start + batch])
        response = await es.mget(index=settings.emails_alias, ids=chunk, source_includes=fields)
        for item in response["docs"]:
            if item.get("found"):
                source = dict(item.get("_source") or {})
                source["id"] = item["_id"]
                out[item["_id"]] = source
    return out
