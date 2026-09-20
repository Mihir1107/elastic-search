"""Search pipeline: parse -> BM25 leg + vector leg -> manual RRF -> page.

Both legs carry the same filters, fusion is manual RRF (k=60), and every stage
is timed so the response can show where the milliseconds went.
"""

from __future__ import annotations

import base64
import binascii
import json
import logging
from time import perf_counter
from typing import Any

from elasticsearch import AsyncElasticsearch

from app.config import Settings
from app.models import (
    Facet,
    SearchHit,
    SearchResponse,
    Timings,
    Understood,
)
from app.search import facets as facets_mod
from app.search.builder import (
    HIGHLIGHT,
    best_highlight,
    build_bm25_query,
    build_filters,
    build_knn,
)
from app.search.embedder import embed_query
from app.search.fusion import FusedHit, fuse
from app.search.parser import ParsedQuery, parse

logger = logging.getLogger(__name__)

_SOURCE_FIELDS = [
    "subject",
    "from",
    "from_name",
    "to",
    "cc",
    "date",
    "thread_id",
    "mailboxes",
    "folder",
    "has_attachment",
    "duplicate_count",
    "body",
]
_FALLBACK_SNIPPET_CHARS = 240


def encode_page_token(offset: int) -> str:
    raw = json.dumps({"o": offset}, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_page_token(token: str | None) -> int:
    if not token:
        return 0
    padded = token + "=" * (-len(token) % 4)
    try:
        payload = json.loads(base64.urlsafe_b64decode(padded.encode()))
        offset = int(payload["o"])
    except (ValueError, KeyError, TypeError, binascii.Error):
        return 0
    return max(0, offset)


def _understood(query: ParsedQuery) -> Understood:
    return Understood(
        terms=list(query.terms),
        phrases=list(query.phrases),
        **{"from": list(query.from_)},
        to=list(query.to),
        cc=list(query.cc),
        subject=list(query.subject),
        after=query.after.isoformat() if query.after else None,
        before=query.before.isoformat() if query.before else None,
    )


def _snippets(hit: FusedHit) -> list[str]:
    fragments = best_highlight(hit.highlight)
    if fragments:
        return fragments
    if hit.chunk:
        return [hit.chunk.strip()]
    body = str(hit.source.get("body") or "").strip()
    if body:
        text = body[:_FALLBACK_SNIPPET_CHARS]
        return [text + ("..." if len(body) > _FALLBACK_SNIPPET_CHARS else "")]
    return []


def _to_hit(hit: FusedHit) -> SearchHit:
    source = hit.source
    return SearchHit(
        id=hit.doc_id,
        score=round(hit.score, 6),
        subject=str(source.get("subject") or ""),
        **{"from": str(source.get("from") or "")},
        from_name=str(source.get("from_name") or ""),
        to=list(source.get("to") or []),
        cc=list(source.get("cc") or []),
        date=source.get("date"),
        thread_id=source.get("thread_id"),
        mailboxes=list(source.get("mailboxes") or []),
        folder=list(source.get("folder") or []),
        has_attachment=bool(source.get("has_attachment", False)),
        duplicate_count=int(source.get("duplicate_count", 1) or 1),
        snippets=_snippets(hit),
        matched_by=hit.matched_by,
    )


async def run_search(
    es: AsyncElasticsearch,
    settings: Settings,
    *,
    q: str,
    size: int | None = None,
    page_token: str | None = None,
) -> SearchResponse:
    started = perf_counter()
    timings = Timings()

    t0 = perf_counter()
    parsed = parse(q)
    timings.parse_ms = round((perf_counter() - t0) * 1000, 2)

    page_size = min(size or settings.default_page_size, settings.max_page_size)
    page_size = max(1, page_size)
    offset = decode_page_token(page_token)
    window = min(max(offset + page_size, page_size), settings.fusion_window)

    filters = build_filters(parsed)
    bm25_query = build_bm25_query(parsed, filters)

    request: dict[str, Any] = {
        "query": bm25_query,
        "size": window,
        "_source": {"includes": _SOURCE_FIELDS},
        "highlight": HIGHLIGHT,
        "aggs": facets_mod.build_aggs(),
        "track_total_hits": True,
    }
    # A pure filter query has no relevance signal, so order by recency instead.
    if not parsed.has_text:
        request["sort"] = [{"date": {"order": "desc", "missing": "_last"}}]

    t0 = perf_counter()
    bm25_response = await es.search(index=settings.emails_alias, **request)
    timings.bm25_ms = round((perf_counter() - t0) * 1000, 2)

    legs: dict[str, list[dict[str, Any]]] = {"bm25": bm25_response["hits"]["hits"]}

    if parsed.semantic_text:
        t0 = perf_counter()
        vector = embed_query(parsed.semantic_text, settings.embed_model, settings.bge_query_prefix)
        timings.embed_ms = round((perf_counter() - t0) * 1000, 2)

        t0 = perf_counter()
        knn_response = await es.search(
            index=settings.emails_alias,
            knn=build_knn(vector, filters, window, settings.knn_num_candidates),
            size=window,
            source={"includes": _SOURCE_FIELDS},
        )
        timings.knn_ms = round((perf_counter() - t0) * 1000, 2)
        legs["knn"] = knn_response["hits"]["hits"]

    t0 = perf_counter()
    fused = fuse(legs)
    timings.fuse_ms = round((perf_counter() - t0) * 1000, 2)

    page = fused[offset : offset + page_size]
    next_token = (
        encode_page_token(offset + page_size)
        if offset + page_size < len(fused) and offset + page_size < settings.fusion_window
        else None
    )

    warnings = list(parsed.warnings)
    if len(fused) >= settings.fusion_window and next_token is None:
        warnings.append(f"pagination is limited to the top {settings.fusion_window} fused results")

    facet_payload = {
        name: [Facet(**bucket) for bucket in buckets]
        for name, buckets in facets_mod.parse_aggs(bm25_response.body).items()
    }

    timings.total_ms = round((perf_counter() - started) * 1000, 2)
    return SearchResponse(
        query=q,
        understood=_understood(parsed),
        total=int(bm25_response["hits"]["total"]["value"]),
        size=page_size,
        hits=[_to_hit(hit) for hit in page],
        facets=facet_payload,
        timings=timings,
        warnings=warnings,
        next_page_token=next_token,
    )
