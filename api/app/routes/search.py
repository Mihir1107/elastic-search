"""GET /search -- the single search box."""

from __future__ import annotations

from fastapi import APIRouter, Query, Request

from app.models import SearchResponse
from app.routes.deps import get_es, get_settings_from
from app.search.service import run_search

router = APIRouter(tags=["search"])


@router.get("/search", response_model=SearchResponse, response_model_by_alias=True)
async def search(
    request: Request,
    q: str = Query("", description='Free text, "phrases", from:/to:/cc:/subject:, before:/after:'),
    size: int | None = Query(None, ge=1, le=200),
    page_token: str | None = Query(None, description="Opaque token from next_page_token"),
    rerank: bool | None = Query(
        None, description="Rerank the top results with a local cross-encoder"
    ),
) -> SearchResponse:
    return await run_search(
        get_es(request),
        get_settings_from(request),
        q=q,
        size=size,
        page_token=page_token,
        rerank=rerank,
    )
