"""GET /export -- the current result set as CSV, for review outside Ledger (D37).

Takes exactly the parameters of /search, and the filters are resolved by the
same code, so an export holds the emails the search showed. What "the result
set" means depends on the query:

* Filters only (a sender, a date range, a review tag, ...): every matching
  email, newest first, up to ``EXPORT_MAX``. This is the review workflow --
  tag while reading, then export ``tag=relevant``.
* Free text or a phrase: the ranked list the search returns, in rank order,
  as deep as pagination reaches (``Settings.fusion_window``). Relevance only
  exists for the fused top of the list; exporting "everything that matches a
  keyword" would silently mean something different from what was on screen.

The response says which it did (``X-Ledger-Export-Mode``) and whether the cap
cut it short (``X-Ledger-Export-Truncated``).
"""

from __future__ import annotations

import csv
import io
from collections.abc import AsyncIterator, Iterable
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse

from app.routes.deps import get_es, get_settings_from
from app.routes.search import structured_filters
from app.search.builder import StructuredFilters, build_bm25_query
from app.search.parser import parse
from app.search.service import resolve_filters, run_search
from app.tags import get_tags

router = APIRouter(tags=["export"])

EXPORT_MAX = 50_000
_PAGE = 1_000
COLUMNS = ["rank", "id", "message_id", "date", "from", "to", "cc", "subject", "thread_id", "tags"]
_FIELDS = ["message_id", "date", "from", "to", "cc", "subject", "thread_id"]
#: Spreadsheet applications execute a cell that starts with one of these. Email
#: content is untrusted, so such cells are prefixed with a quote (OWASP: CSV
#: injection) -- a subject line must never become a formula on a reviewer's machine.
_FORMULA_START = ("=", "+", "-", "@", "\t", "\r")


def _cell(value: Any) -> str:
    if isinstance(value, list):
        value = "; ".join(str(v) for v in value)
    text = "" if value is None else str(value)
    return f"'{text}" if text.startswith(_FORMULA_START) else text


def _csv_line(values: Iterable[Any]) -> str:
    buffer = io.StringIO()
    csv.writer(buffer).writerow([_cell(v) for v in values])
    return buffer.getvalue()


@router.get("/export")
async def export(
    request: Request,
    q: str = Query("", description="Same query string as /search"),
    rerank: bool | None = Query(None, description="Export the reranked order, as /search"),
    structured: StructuredFilters = Depends(structured_filters),
) -> StreamingResponse:
    es, settings = get_es(request), get_settings_from(request)
    parsed = parse(q)
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    headers = {"content-disposition": f'attachment; filename="ledger-export-{stamp}.csv"'}

    if parsed.has_text:
        headers["x-ledger-export-mode"] = "ranked"
        headers["x-ledger-export-truncated"] = "false"
        rows = _ranked_rows(request, q, rerank, structured)
    else:
        filters, _ = await resolve_filters(es, settings, parsed, structured)
        query = build_bm25_query(parsed, filters)
        total = int((await es.count(index=settings.emails_alias, query=query))["count"])
        headers["x-ledger-export-mode"] = "complete"
        headers["x-ledger-export-truncated"] = str(total > EXPORT_MAX).lower()
        rows = _filtered_rows(request, query)

    async def body() -> AsyncIterator[str]:
        yield _csv_line(COLUMNS)
        async for row in rows:
            yield _csv_line(row)

    return StreamingResponse(body(), media_type="text/csv; charset=utf-8", headers=headers)


async def _ranked_rows(
    request: Request, q: str, rerank: bool | None, structured: StructuredFilters
) -> AsyncIterator[list[Any]]:
    es, settings = get_es(request), get_settings_from(request)
    token: str | None = None
    rank = 0
    while True:
        page = await run_search(
            es,
            settings,
            q=q,
            size=settings.max_page_size,
            page_token=token,
            rerank=rerank,
            structured=structured,
        )
        for hit in page.hits:
            rank += 1
            data = hit.model_dump(by_alias=True)
            yield [rank, hit.id, *(data.get(f) for f in _FIELDS), hit.tags]
        token = page.next_page_token
        if not token:
            return


async def _filtered_rows(request: Request, query: dict[str, Any]) -> AsyncIterator[list[Any]]:
    es, settings = get_es(request), get_settings_from(request)
    search_after: list[Any] | None = None
    written = 0
    while written < EXPORT_MAX:
        extra: dict[str, Any] = {"search_after": search_after} if search_after else {}
        response = await es.search(
            index=settings.emails_alias,
            query=query,
            size=min(_PAGE, EXPORT_MAX - written),
            source={"includes": _FIELDS},
            # Newest first, with the unique message_id as a total-order tiebreak
            # so search_after never skips or repeats an email between pages.
            sort=[
                {"date": {"order": "desc", "missing": "_last"}},
                {"message_id": {"order": "asc", "missing": "_last"}},
            ],
            **extra,
        )
        hits = response["hits"]["hits"]
        if not hits:
            return
        tags = await get_tags(es, settings.tags_index, [h["_id"] for h in hits])
        for hit in hits:
            written += 1
            source = hit["_source"]
            yield [written, hit["_id"], *(source.get(f) for f in _FIELDS), tags.get(hit["_id"], [])]
        search_after = hits[-1]["sort"]
