"""GET /search -- the single search box, plus facet filters."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.models import SearchResponse
from app.routes.deps import get_es, get_settings_from
from app.search.builder import StructuredFilters
from app.search.parser import MAX_VALUES_PER_FIELD
from app.search.service import run_search
from app.tags import normalise_tags

router = APIRouter(tags=["search"])


def structured_filters(
    # Structured filters. These are what the UI sends when a facet is clicked;
    # repeating a parameter ORs its values, and different parameters AND.
    from_: list[str] | None = Query(None, alias="from", description="Sender address"),
    to: list[str] | None = Query(None, description="Recipient address"),
    cc: list[str] | None = Query(None, description="CC address"),
    folder: list[str] | None = Query(None, description="Mailbox folder"),
    after: date | None = Query(None, description="Inclusive lower date bound"),
    before: date | None = Query(None, description="Inclusive upper date bound"),
    has_attachment: bool | None = Query(None),
    tag: list[str] | None = Query(None, description="Review tag (any of them)"),
) -> StructuredFilters:
    """The facet filters, shared by /search and /export so both mean the same thing.

    Bounded like the query string's operators: each value becomes a clause, and
    an unbounded list would be an unbounded Elasticsearch request.
    """
    for name, values in (("from", from_), ("to", to), ("cc", cc), ("folder", folder), ("tag", tag)):
        if values and len(values) > MAX_VALUES_PER_FIELD:
            raise HTTPException(
                status_code=422, detail=f"at most {MAX_VALUES_PER_FIELD} {name} values"
            )
    return StructuredFilters(
        from_=tuple(v.strip().lower() for v in from_ or () if v.strip()),
        to=tuple(v.strip().lower() for v in to or () if v.strip()),
        cc=tuple(v.strip().lower() for v in cc or () if v.strip()),
        folder=tuple(v for v in folder or () if v),
        after=after,
        before=before,
        has_attachment=has_attachment,
        # Validated here, so a malformed tag is a 422 rather than a failure
        # deep inside the tag lookup.
        tags=tuple(normalise_tags(t for t in tag or () if t.strip())),
    )


@router.get("/search", response_model=SearchResponse, response_model_by_alias=True)
async def search(
    request: Request,
    q: str = Query("", description='Free text, "phrases", from:/to:/cc:/subject:, before:/after:'),
    size: int | None = Query(None, ge=1, le=200, description="Capped at max_page_size"),
    page_token: str | None = Query(None, description="Opaque token from next_page_token"),
    rerank: bool | None = Query(
        None, description="Rerank the top results with a local cross-encoder"
    ),
    structured: StructuredFilters = Depends(structured_filters),
) -> SearchResponse:
    return await run_search(
        get_es(request),
        get_settings_from(request),
        q=q,
        size=size,
        page_token=page_token,
        rerank=rerank,
        structured=structured,
    )
