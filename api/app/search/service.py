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
from collections import OrderedDict
from collections.abc import Hashable
from dataclasses import dataclass, replace
from time import monotonic, perf_counter
from typing import Any, Literal

from elasticsearch import AsyncElasticsearch

from app.config import Settings
from app.models import (
    Correction,
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
    phrase_filters,
)
from app.search.embedder import embed_query, is_known_word
from app.search.fusion import FusedHit, fuse
from app.search.parser import ParsedQuery, parse
from app.search.rerank import rerank as rerank_hits
from app.search.spelling import build_suggest, corrected_text
from app.search.spelling import corrections as find_corrections
from app.tags import generation as tag_generation
from app.tags import get_tags, ids_with_tags

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
#: What the cross-encoder reads (rerank.document_text).
_RERANK_FIELDS = ["subject", "body"]
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


def _understood(query: ParsedQuery, corrections: list[Correction] | None = None) -> Understood:
    return Understood(
        terms=list(query.terms),
        phrases=list(query.phrases),
        **{"from": list(query.from_)},
        to=list(query.to),
        cc=list(query.cc),
        subject=list(query.subject),
        after=query.after.isoformat() if query.after else None,
        before=query.before.isoformat() if query.before else None,
        corrections=corrections or [],
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


def _to_hit(hit: FusedHit, tags: list[str] | None = None) -> SearchHit:
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
        tags=tags or [],
    )


async def resolve_filters(
    es: AsyncElasticsearch,
    settings: Settings,
    parsed: ParsedQuery,
    structured: StructuredFilters | None,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Every filter a search applies, and any warnings resolving them raised.

    Shared with export, so an export holds exactly the emails the search did.
    Review tags live in their own index (D37), so a tag filter becomes an ids
    filter over the emails carrying the tag -- an empty one when none do.
    """
    filters = build_filters(parsed)
    warnings: list[str] = []
    if structured is not None:
        # Facet clicks AND with whatever the query string already said.
        filters = filters + build_structured_filters(structured)
        if structured.tags:
            ids, truncated = await ids_with_tags(es, settings.tags_index, structured.tags)
            filters.append({"ids": {"values": ids}})
            if truncated:
                warnings.append(f"tag filter limited to the first {len(ids)} tagged emails")
    return filters, warnings


async def _hydrate(
    es: AsyncElasticsearch,
    settings: Settings,
    hits: list[FusedHit],
    *,
    fields: list[str],
    preference: str,
    highlight_query: dict[str, Any] | None = None,
) -> None:
    """Load ``fields`` for ``hits``, in place, highlighting keyword matches.

    With ``highlight_query``, documents the keyword leg matched are fetched by
    an id-filtered search that also highlights them; highlighting costs per
    document, so it is never spent on semantic-only hits, which keep their
    chunk snippet. Everything else is a plain multi-get. The two run
    concurrently, so hydration costs the slower of them, not the sum.
    """
    keyword = [h for h in hits if highlight_query is not None and "bm25" in h.ranks]
    keyword_ids = {h.doc_id for h in keyword}
    plain = [h for h in hits if h.doc_id not in keyword_ids]

    async def highlighted() -> list[dict[str, Any]]:
        if not keyword:
            return []
        response = await es.search(
            index=settings.emails_alias,
            query={
                "bool": {
                    "must": [highlight_query],
                    "filter": [{"ids": {"values": [h.doc_id for h in keyword]}}],
                }
            },
            size=len(keyword),
            source={"includes": fields},
            highlight=HIGHLIGHT,
            preference=preference,
        )
        return list(response["hits"]["hits"])

    async def fetched() -> list[dict[str, Any]]:
        if not plain:
            return []
        response = await es.mget(
            index=settings.emails_alias,
            ids=[h.doc_id for h in plain],
            source_includes=fields,
            preference=preference,
        )
        return [d for d in response["docs"] if d.get("found")]

    found = [doc for docs in await asyncio.gather(highlighted(), fetched()) for doc in docs]
    loaded = {doc["_id"]: doc for doc in found}
    for hit in hits:
        doc = loaded.get(hit.doc_id)
        if doc is None:
            continue
        hit.source = {**hit.source, **(doc.get("_source") or {})}
        if doc.get("highlight"):
            hit.highlight = doc["highlight"]


@dataclass
class _Candidates:
    """Everything about a search except which page of it is shown.

    Cached, so that later pages and exports reuse the fused list instead of
    re-running both retrieval legs, the facets, the embedder and the reranker
    to show twenty more rows.
    """

    parsed: ParsedQuery
    fused: list[FusedHit]
    bm25_query: dict[str, Any]
    bm25_total: int
    has_bm25_leg: bool
    facets: dict[str, list[Facet]]
    corrections: list[Correction]
    warnings: list[str]
    timings: Timings


class _ResultCache:
    """Bounded, time-limited cache of fused candidate lists. Event-loop only."""

    def __init__(self, size: int, ttl_s: float) -> None:
        self.size, self.ttl_s = size, ttl_s
        self._data: OrderedDict[Hashable, tuple[float, _Candidates]] = OrderedDict()

    def get(self, key: Hashable) -> _Candidates | None:
        entry = self._data.get(key)
        if entry is None:
            return None
        stored, value = entry
        if monotonic() - stored > self.ttl_s:
            del self._data[key]
            return None
        self._data.move_to_end(key)
        return value

    def put(self, key: Hashable, value: _Candidates) -> None:
        if self.size <= 0:
            return
        self._data[key] = (monotonic(), value)
        self._data.move_to_end(key)
        while len(self._data) > self.size:
            self._data.popitem(last=False)

    def clear(self) -> None:
        self._data.clear()


_results = _ResultCache(256, 300.0)


def configure_cache(size: int, ttl_s: float) -> None:
    """Apply ``Settings.result_cache_*``."""
    _results.size, _results.ttl_s = size, ttl_s


def reset_cache() -> None:
    """Test hook."""
    _results.clear()


def _timed_embed(text: str, settings: Settings) -> tuple[list[float], float]:
    t0 = perf_counter()
    vector = embed_query(text, settings.embed_model, settings.bge_query_prefix)
    return vector, round((perf_counter() - t0) * 1000, 2)


async def _retrieve(
    es: AsyncElasticsearch,
    settings: Settings,
    *,
    q: str,
    method: Literal["hybrid", "bm25", "vector"],
    use_rerank: bool,
    structured: StructuredFilters | None,
) -> _Candidates:
    """Parse, run both legs, fuse and (optionally) rerank: the whole ranked list."""
    timings = Timings()

    t0 = perf_counter()
    parsed = parse(q)
    timings.parse_ms = round((perf_counter() - t0) * 1000, 2)

    # The fusion window is a constant for a query, never a function of the page.
    # RRF ranks a document against the other candidates it was fused with, so
    # growing the window per page reshuffles the whole list: fused[20:40] taken
    # from a 40-document window is not a continuation of fused[0:20] taken from
    # a 20-document window, and page two repeats results page one already showed.
    window = settings.fusion_window

    filters, filter_warnings = await resolve_filters(es, settings, parsed, structured)
    bm25_query = build_bm25_query(
        parsed, filters, settings.bm25_fields, settings.bm25_minimum_should_match
    )

    # No highlighting and no documents on the retrieval legs. Fusion needs a
    # wide candidate set, but only ids and ranks; the page is what gets shown.
    # Highlighting is per document (measured at size 200: 8.6ms without, 158.8ms
    # with), and so is _source: bodies made each leg's response ~380KB for the
    # ~20 documents a page uses (D35). So the window is fetched bare and the page
    # is hydrated and highlighted by a second, id-filtered query below.
    request: dict[str, Any] = {
        "query": bm25_query,
        "size": window,
        "_source": False,
        "aggs": facets_mod.build_aggs(),
        "track_total_hits": True,
    }
    suggest = build_suggest(parsed) if settings.spell_correct_embedding else None
    if suggest:
        request["suggest"] = suggest
    tiebreak = {"message_id": {"order": "asc", "missing": "_last"}}
    if parsed.has_text:
        request["sort"] = [{"_score": {"order": "desc"}}, tiebreak]
    else:
        # A pure filter query has no relevance signal, so order by recency.
        request["sort"] = [{"date": {"order": "desc", "missing": "_last"}}, tiebreak]

    wants_vector = method in ("hybrid", "vector")
    # Embed the query while the BM25 leg is in flight. Spelling correction
    # needs the BM25 response, but it changes the text only for a misspelled
    # query; the common case uses the vector computed here, so the model's time
    # overlaps the network's instead of adding to it. Off the event loop:
    # encoding is synchronous CPU work (measured, concurrency 1 -> 8: p50 wall
    # 46.6ms -> 159.6ms with it inline), and torch releases the GIL.
    speculative: asyncio.Task[tuple[list[float], float]] | None = None
    if wants_vector and parsed.semantic_text:
        speculative = asyncio.create_task(
            asyncio.to_thread(_timed_embed, parsed.semantic_text, settings)
        )

    preference = _preference_for(q)
    try:
        t0 = perf_counter()
        bm25_response = await es.search(
            index=settings.emails_alias, preference=preference, **request
        )
        timings.bm25_ms = round((perf_counter() - t0) * 1000, 2)

        legs: dict[str, list[dict[str, Any]]] = {}
        if method in ("hybrid", "bm25"):
            legs["bm25"] = bm25_response["hits"]["hits"]

        fixes = find_corrections(
            parsed,
            bm25_response.body,
            lambda word: is_known_word(word, settings.embed_model),
        )
        semantic_text = corrected_text(parsed, fixes) if fixes else parsed.semantic_text
        corrections = [Correction(original=f.original, suggested=f.suggested) for f in fixes]

        if semantic_text and wants_vector:
            if speculative is not None and semantic_text == parsed.semantic_text:
                vector, timings.embed_ms = await speculative
            else:
                if speculative is not None:
                    speculative.cancel()  # the thread finishes; its result is dropped
                vector, timings.embed_ms = await asyncio.to_thread(
                    _timed_embed, semantic_text, settings
                )
            speculative = None

            t0 = perf_counter()
            knn_response = await es.search(
                index=settings.emails_alias,
                # A quoted phrase is a requirement on both legs (D35).
                knn=build_knn(
                    vector, filters + phrase_filters(parsed), window, settings.knn_num_candidates
                ),
                size=window,
                source=False,
                preference=preference,
            )
            timings.knn_ms = round((perf_counter() - t0) * 1000, 2)
            legs["knn"] = knn_response["hits"]["hits"]
    finally:
        if speculative is not None:
            speculative.cancel()

    t0 = perf_counter()
    fused = fuse(legs)
    timings.fuse_ms = round((perf_counter() - t0) * 1000, 2)

    warnings = [*parsed.warnings, *filter_warnings]
    if use_rerank and settings.rerank_free_text_only and (parsed.phrases or parsed.has_filters):
        # The user gave an explicit precision signal; do not let a semantic
        # reranker talk us out of it (D23). Say so: a skipped rerank that
        # returns the same results with no explanation looks like a broken one.
        use_rerank = False
        warnings.append(
            "reranking skipped: the query has a quoted phrase or a field operator, "
            "and the reranker never overrides an explicit precision signal"
        )
    if use_rerank and semantic_text and fused:
        t0 = perf_counter()
        # The cross-encoder reads subject and body, which retrieval no longer
        # fetches; loading them is part of what reranking costs.
        await _hydrate(
            es,
            settings,
            fused[: settings.rerank_window],
            fields=_RERANK_FIELDS,
            preference=preference,
        )
        # Same reasoning as the embedder: the cross-encoder is heavier still.
        fused = await asyncio.to_thread(
            rerank_hits,
            semantic_text,
            fused,
            settings.rerank_model,
            settings.rerank_window,
        )
        timings.rerank_ms = round((perf_counter() - t0) * 1000, 2)
        # The bodies were only for the cross-encoder; do not keep them cached.
        for hit in fused:
            hit.source = {}

    if len(fused) >= settings.fusion_window:
        warnings.append(f"pagination is limited to the top {settings.fusion_window} fused results")

    return _Candidates(
        parsed=parsed,
        fused=fused,
        bm25_query=bm25_query,
        bm25_total=int(bm25_response["hits"]["total"]["value"]),
        has_bm25_leg="bm25" in legs,
        facets={
            name: [Facet(**bucket) for bucket in buckets]
            for name, buckets in facets_mod.parse_aggs(bm25_response.body).items()
        },
        corrections=corrections,
        warnings=warnings,
        timings=timings,
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
    """Run the search pipeline and return one page of it.

    ``method`` exists so the evaluation harness can measure each retrieval leg in
    isolation against exactly the query construction production uses, rather
    than re-implementing it. The HTTP API always uses the default, "hybrid".

    A first page always runs the full pipeline, so its timings (and every
    benchmark and evaluation) measure real work. A later page reuses the fused
    list its first page cached, when it is still there.
    """
    started = perf_counter()
    requested = size or settings.default_page_size
    page_size = max(1, min(requested, settings.max_page_size))
    offset = decode_page_token(page_token)
    use_rerank = settings.rerank_enabled if rerank is None else rerank

    key = (q, structured, method, use_rerank, tag_generation())
    candidates = _results.get(key) if page_token else None
    cached = candidates is not None
    if candidates is None:
        candidates = await _retrieve(
            es, settings, q=q, method=method, use_rerank=use_rerank, structured=structured
        )
        _results.put(key, candidates)
    parsed, fused = candidates.parsed, candidates.fused
    timings = Timings() if cached else candidates.timings.model_copy()

    # Copies: hydration writes documents into the hits, and the cached list
    # should hold ranks, not bodies.
    page = [
        replace(hit, source=dict(hit.source), highlight=dict(hit.highlight), ranks=dict(hit.ranks))
        for hit in fused[offset : offset + page_size]
    ]

    preference = _preference_for(q)
    if page:
        t0 = perf_counter()
        hydration = _hydrate(
            es,
            settings,
            page,
            fields=_SOURCE_FIELDS,
            preference=preference,
            highlight_query=candidates.bm25_query if parsed.has_text else None,
        )
        _, page_tags = await asyncio.gather(
            hydration, get_tags(es, settings.tags_index, [hit.doc_id for hit in page])
        )
        timings.highlight_ms = round((perf_counter() - t0) * 1000, 2)
    else:
        page_tags = {}

    next_token = (
        encode_page_token(offset + page_size)
        if offset + page_size < len(fused) and offset + page_size < settings.fusion_window
        else None
    )

    warnings = list(candidates.warnings)
    if requested > settings.max_page_size:
        warnings.append(f"page size capped at {settings.max_page_size}")

    # The BM25 leg's exact count is the meaningful "how many emails match"
    # (DECISIONS D16), but it describes only that leg. A semantic-only query --
    # keywords that match nothing while the vector leg finds plenty -- would
    # otherwise report 0 above a page of results. Never under-report what was
    # actually returned.
    total = candidates.bm25_total if candidates.has_bm25_leg else 0
    total = max(total, len(fused))

    timings.total_ms = round((perf_counter() - started) * 1000, 2)
    return SearchResponse(
        query=q,
        understood=_understood(parsed, candidates.corrections),
        total=total,
        size=page_size,
        hits=[_to_hit(hit, page_tags.get(hit.doc_id)) for hit in page],
        facets=candidates.facets,
        timings=timings,
        warnings=warnings,
        next_page_token=next_token,
        reranked=bool(candidates.timings.rerank_ms),
    )
