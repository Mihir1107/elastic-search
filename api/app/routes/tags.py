"""Review tags: set an email's tags, tag many at once, list what is in use (D37)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from app.models import (
    BatchTagsRequest,
    BatchTagsResponse,
    ChangeTagsRequest,
    EmailTags,
    SetTagsRequest,
    TagCount,
    TagsResponse,
)
from app.routes.deps import get_es, get_settings_from
from app.tags import MAX_BATCH, batch_tags, change_tags, set_tags, tag_counts

router = APIRouter(tags=["tags"])

_MAX_REVIEWER_CHARS = 64


def reviewer(request: Request) -> str:
    """Who is tagging: the user the web tier authenticated, passed as a header.

    Attribution, not authorisation -- the API key is what gates access.
    """
    raw = request.headers.get("x-ledger-user", "")
    return "".join(ch for ch in raw if ch.isprintable())[:_MAX_REVIEWER_CHARS]


async def _require_email(request: Request, email_id: str) -> None:
    es, settings = get_es(request), get_settings_from(request)
    if not await es.exists(index=settings.emails_alias, id=email_id):
        raise HTTPException(status_code=404, detail=f"email {email_id} not found")


@router.get("/tags", response_model=TagsResponse)
async def list_tags(request: Request) -> TagsResponse:
    counts = await tag_counts(get_es(request), get_settings_from(request).tags_index)
    return TagsResponse(tags=[TagCount(**c) for c in counts])


@router.put("/emails/{email_id}/tags", response_model=EmailTags)
async def put_tags(request: Request, email_id: str, body: SetTagsRequest) -> EmailTags:
    """Replace the email's tags; an empty list clears them. Last write wins."""
    es, settings = get_es(request), get_settings_from(request)
    await _require_email(request, email_id)
    tags = await set_tags(es, settings.tags_index, email_id, body.tags, reviewer(request))
    return EmailTags(id=email_id, tags=tags)


@router.patch("/emails/{email_id}/tags", response_model=EmailTags)
async def patch_tags(request: Request, email_id: str, body: ChangeTagsRequest) -> EmailTags:
    """Add and remove tags atomically; a concurrent reviewer's change is kept."""
    es, settings = get_es(request), get_settings_from(request)
    await _require_email(request, email_id)
    tags = await change_tags(
        es, settings.tags_index, email_id, body.add, body.remove, reviewer(request)
    )
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
    updated = await batch_tags(
        es, settings.tags_index, ids, body.add, body.remove, reviewer(request)
    )
    return BatchTagsResponse(updated=updated)
