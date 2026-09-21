"""Review tags: set an email's tags, tag many at once, list what is in use (D37)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from app.models import (
    BatchTagsRequest,
    BatchTagsResponse,
    EmailTags,
    SetTagsRequest,
    TagCount,
    TagsResponse,
)
from app.routes.deps import get_es, get_settings_from
from app.tags import MAX_BATCH, TagError, batch_tags, set_tags, tag_counts

router = APIRouter(tags=["tags"])


@router.get("/tags", response_model=TagsResponse)
async def list_tags(request: Request) -> TagsResponse:
    counts = await tag_counts(get_es(request), get_settings_from(request).tags_index)
    return TagsResponse(tags=[TagCount(**c) for c in counts])


@router.put("/emails/{email_id}/tags", response_model=EmailTags)
async def put_tags(request: Request, email_id: str, body: SetTagsRequest) -> EmailTags:
    """Replace the email's tags; an empty list clears them."""
    es, settings = get_es(request), get_settings_from(request)
    if not await es.exists(index=settings.emails_alias, id=email_id):
        raise HTTPException(status_code=404, detail=f"email {email_id} not found")
    try:
        tags = await set_tags(es, settings.tags_index, email_id, body.tags)
    except TagError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return EmailTags(id=email_id, tags=tags)


@router.post("/tags/batch", response_model=BatchTagsResponse)
async def post_batch(request: Request, body: BatchTagsRequest) -> BatchTagsResponse:
    """Add and remove tags across many emails; ids that are not emails are skipped."""
    es, settings = get_es(request), get_settings_from(request)
    ids = list(dict.fromkeys(body.ids))
    if len(ids) > MAX_BATCH:
        raise HTTPException(status_code=422, detail=f"at most {MAX_BATCH} emails per batch")
    if ids:
        found = await es.mget(index=settings.emails_alias, ids=ids, source=False)
        ids = [doc["_id"] for doc in found["docs"] if doc.get("found")]
    try:
        updated = await batch_tags(es, settings.tags_index, ids, body.add, body.remove)
    except TagError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return BatchTagsResponse(updated=updated)
