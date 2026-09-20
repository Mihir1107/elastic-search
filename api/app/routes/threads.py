"""GET /threads/{thread_id} -- a whole conversation in order."""

from __future__ import annotations

from time import perf_counter

from fastapi import APIRouter, HTTPException, Query, Request

from app.models import EmailDetail, ThreadResponse, Timings
from app.routes.deps import get_es, get_settings_from

router = APIRouter(tags=["threads"])
MAX_THREAD_MESSAGES = 500


@router.get("/threads/{thread_id}", response_model=ThreadResponse, response_model_by_alias=True)
async def get_thread(
    request: Request,
    thread_id: str,
    size: int = Query(100, ge=1, le=MAX_THREAD_MESSAGES),
) -> ThreadResponse:
    es = get_es(request)
    settings = get_settings_from(request)
    started = perf_counter()
    response = await es.search(
        index=settings.emails_alias,
        query={"term": {"thread_id": thread_id}},
        sort=[{"date": {"order": "asc", "missing": "_last"}}],
        size=size,
        source_excludes=["chunks"],
        track_total_hits=True,
    )
    total = int(response["hits"]["total"]["value"])
    if total == 0:
        raise HTTPException(status_code=404, detail=f"thread {thread_id} not found")
    messages = [
        EmailDetail(id=hit["_id"], **dict(hit["_source"])) for hit in response["hits"]["hits"]
    ]
    return ThreadResponse(
        thread_id=thread_id,
        total=total,
        messages=messages,
        timings=Timings(total_ms=round((perf_counter() - started) * 1000, 2)),
    )
