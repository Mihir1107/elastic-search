"""GET /emails/{id} -- one full email."""

from __future__ import annotations

import asyncio

from elasticsearch import NotFoundError
from fastapi import APIRouter, HTTPException, Request

from app.models import EmailDetail
from app.names import display_name
from app.routes.deps import get_es, get_settings_from
from app.tags import get_tags

router = APIRouter(tags=["emails"])


@router.get("/emails/{email_id}", response_model=EmailDetail, response_model_by_alias=True)
async def get_email(request: Request, email_id: str) -> EmailDetail:
    es = get_es(request)
    settings = get_settings_from(request)
    # The document and its tags are independent reads: fetch them together.
    try:
        doc, tags = await asyncio.gather(
            es.get(index=settings.emails_alias, id=email_id, source_excludes=["chunks"]),
            get_tags(es, settings.tags_index, [email_id]),
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"email {email_id} not found") from exc
    source = dict(doc["_source"])
    source["from_name"] = display_name(str(source.get("from_name") or ""))
    source["tags"] = tags.get(email_id, [])
    return EmailDetail(id=email_id, **source)
