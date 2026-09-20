"""Search pipeline: parse -> BM25 leg + vector leg -> manual RRF -> page.

Both legs carry the same filters, fusion is manual RRF (k=60), and every stage
is timed so the response can show where the milliseconds went.

Pagination consistency: each page re-runs the search, and with replicas the
coordinating node may pick a different shard copy each time. Copies hold the
same documents but lay them out in different segments, so equal-scoring hits
come back in a different order and an offset-based page can repeat or skip
results. Two things pin the order down: a ``preference`` derived from the query
(so every page of one search reads the same copies) and an explicit tiebreaker
on the unique ``message_id`` (so equal scores still have one total order).
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import hashlib
import json
import logging
from time import perf_counter
from typing import Any, Literal

from elasticsearch import AsyncElasticsearch

from app.config import Settings
from app.models import (
    Facet,
    SearchHit,
    SearchResponse,
    Timings,
    Understood,
)
from app.names import display_name
from app.search import facets as facets_mod
from app.search.builder import (
    HIGHLIGHT,
    StructuredFilters,
    best_highlight,
    build_bm25_query,
    build_filters,
    build_knn,
    build_structured_filters,
)
from app.search.embedder import embed_query
from app.search.fusion import FusedHit, fuse
from app.search.parser import ParsedQuery, parse
from app.search.rerank import rerank as rerank_hits

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
    "message_id",
    "attachment_names",
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


def _preference_for(raw_query: str) -> str:
    """Stable shard-copy preference so all pages of one search agree."""
    return "ledger-" + hashlib.sha1(raw_query.encode("utf-8")).hexdigest()[:16]


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
        from_name=display_name(str(source.get("from_name") or "")),
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
        message_id=str(source.get("message_id") or ""),
        attachment_names=list(source.get("attachment_names") or []),
        # Real per-leg positions, so the UI can show why a hit surfaced rather
        # than approximating from its position in the fused list.
        bm25_rank=hit.ranks.get("bm25"),
        vector_rank=hit.ranks.get("knn"),
    )


async def run_search(
    es: AsyncElasticsearch,
    settings: Settings,
    *,
    q: str,
    size: int | None = None,
    page_token: str | None = None,
    method: Literal["hybrid", "bm25", "vector"] = "hybrid",
    rerank: bool | None = None,
    structured: StructuredFilters | None = None,
) -> SearchResponse:
    """Run the search pipeline.

    ``method`` exists so the evaluation harness can measure each retrieval leg in
    isolation against exactly the query construction production uses, rather
    than re-implementing it. The HTTP API always uses the default, "hybrid".
    """
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
    if structured is not None:
        # Facet clicks AND with whatever the query string already said.
        filters = filters + build_structured_filters(structured)
    bm25_query = build_bm25_query(parsed, filters, settings.bm25_fields)

    request: dict[str, Any] = {
        "query": bm25_query,
        "size": window,
        "_source": {"includes": _SOURCE_FIELDS},
        "aggs": facets_mod.build_aggs(),
        "highlight": HIGHLIGHT,
        "track_total_hits": True,
    }
    tiebreak = {"message_id": {"order": "asc", "missing": "_last"}}
    if parsed.has_text:
        request["sort"] = [{"_score": {"order": "desc"}}, tiebreak]
    else:
        # A pure filter query has no relevance signal, so order by recency.
        request["sort"] = [{"date": {"order": "desc", "missing": "_last"}}, tiebreak]

    preference = _preference_for(q)
    t0 = perf_counter()
    bm25_response = await es.search(index=settings.emails_alias, preference=preference, **request)
    timings.bm25_ms = round((perf_counter() - t0) * 1000, 2)

    legs: dict[str, list[dict[str, Any]]] = {}
    if method in ("hybrid", "bm25"):
        legs["bm25"] = bm25_response["hits"]["hits"]

    if parsed.semantic_text and method in ("hybrid", "vector"):
        t0 = perf_counter()
        # Off the event loop: encoding is synchronous CPU work, and running it
        # inline stalls every other in-flight request for its whole duration.
        # Measured on the dev subset, concurrency 1 -> 8: p50 wall 46.6ms ->
        # 159.6ms with the call inline, while embed_ms itself stayed flat --
        # the cost was other requests queueing behind it, not the model.
        # torch releases the GIL inside the forward pass, so a worker thread
        # genuinely overlaps with the event loop's I/O.
        vector = await asyncio.to_thread(
            embed_query, parsed.semantic_text, settings.embed_model, settings.bge_query_prefix
        )
        timings.embed_ms = round((perf_counter() - t0) * 1000, 2)

        t0 = perf_counter()
        knn_response = await es.search(
            index=settings.emails_alias,
            knn=build_knn(vector, filters, window, settings.knn_num_candidates),
            size=window,
            source={"includes": _SOURCE_FIELDS},
            preference=preference,
        )
        timings.knn_ms = round((perf_counter() - t0) * 1000, 2)
        legs["knn"] = knn_response["hits"]["hits"]

    t0 = perf_counter()
    fused = fuse(legs)
    timings.fuse_ms = round((perf_counter() - t0) * 1000, 2)

    # Reranking is a request flag over a config default, and its cost is reported
    # separately so it can never hide inside total_ms (kickoff section 6).
    use_rerank = settings.rerank_enabled if rerank is None else rerank
    if use_rerank and settings.rerank_free_text_only and (parsed.phrases or parsed.has_filters):
        # The user gave an explicit precision signal; do not let a semantic
        # reranker talk us out of it.
        use_rerank = False
    if use_rerank and parsed.semantic_text and fused:
        t0 = perf_counter()
        # Same reasoning as the embedder: the cross-encoder is heavier still.
        fused = await asyncio.to_thread(
            rerank_hits,
            parsed.semantic_text,
            fused,
            settings.rerank_model,
            settings.rerank_window,
        )
        timings.rerank_ms = round((perf_counter() - t0) * 1000, 2)

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

    # The BM25 leg's exact count is the meaningful "how many emails match"
    # (DECISIONS D16), but it describes only that leg. A semantic-only query --
    # keywords that match nothing while the vector leg finds plenty -- would
    # otherwise report 0 above a page of results. Never under-report what was
    # actually returned.
    bm25_total = int(bm25_response["hits"]["total"]["value"])
    total = bm25_total if "bm25" in legs else 0
    total = max(total, len(fused))

    timings.total_ms = round((perf_counter() - started) * 1000, 2)
    return SearchResponse(
        query=q,
        understood=_understood(parsed),
        total=total,
        size=page_size,
        hits=[_to_hit(hit) for hit in page],
        facets=facet_payload,
        timings=timings,
        warnings=warnings,
        next_page_token=next_token,
        reranked=bool(timings.rerank_ms),
    )
