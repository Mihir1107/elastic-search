"""GET /suggest -- autocomplete over people and subjects.

Implemented with a terms aggregation (people) plus ``match_phrase_prefix``
(subjects) rather than a ``search_as_you_type`` field. Same behaviour for the
caller, but it needs no mapping change and therefore no second copy of the index
-- which matters on a disk-constrained machine. Switching to
``search_as_you_type`` later is a mapping bump plus one reindex behind the alias.
"""

from __future__ import annotations

import re
from time import perf_counter

from fastapi import APIRouter, Query, Request

from app.models import Suggestion, SuggestResponse, Timings
from app.routes.deps import get_es, get_settings_from

router = APIRouter(tags=["suggest"])

#: A terms-aggregation ``include`` is a regular expression, so user input is
#: reduced to a safe character class before it goes near one (spec flaw #13).
_SAFE = re.compile(r"[^a-z0-9._@'-]")
MAX_PREFIX = 64


@router.get("/suggest", response_model=SuggestResponse)
async def suggest(
    request: Request,
    prefix: str = Query("", description="What the user has typed so far"),
    size: int = Query(5, ge=1, le=20),
) -> SuggestResponse:
    es = get_es(request)
    settings = get_settings_from(request)
    started = perf_counter()

    def _timings() -> Timings:
        return Timings(total_ms=round((perf_counter() - started) * 1000, 2))

    cleaned = _SAFE.sub("", prefix.lower())[:MAX_PREFIX]
    if not cleaned:
        return SuggestResponse(prefix=prefix, suggestions=[], timings=_timings())

    response = await es.search(
        index=settings.emails_alias,
        size=size,
        query={"match_phrase_prefix": {"subject": {"query": prefix, "max_expansions": 20}}},
        source={"includes": ["subject"]},
        aggs={"people": {"terms": {"field": "from", "include": f"{cleaned}.*", "size": size}}},
    )

    suggestions: list[Suggestion] = [
        Suggestion(value=str(b["key"]), kind="person", count=int(b["doc_count"]))
        for b in response["aggregations"]["people"]["buckets"]
    ]

    seen: set[str] = set()
    for hit in response["hits"]["hits"]:
        subject = str((hit.get("_source") or {}).get("subject") or "").strip()
        if subject and subject.lower() not in seen:
            seen.add(subject.lower())
            suggestions.append(Suggestion(value=subject, kind="subject"))

    return SuggestResponse(prefix=prefix, suggestions=suggestions[: size * 2], timings=_timings())
