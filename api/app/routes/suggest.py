"""GET /suggest -- autocomplete over people and subjects.

Two independent searches in one ``msearch`` round trip: senders whose address
starts with the prefix (a ``prefix`` query plus a terms aggregation over the
matches), and subjects by ``match_phrase_prefix``. They must be separate
requests: an aggregation counts the documents its own query matched, so when
the two shared one query the people came only from emails whose *subject*
matched the prefix -- "kenneth.lay" suggested nobody. Rather than a
``search_as_you_type`` field. Same behaviour for the
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

#: Addresses are made of these; anything else cannot start one. No regex is
#: built from the input any more, but the character class still keeps the
#: prefix query to plausible addresses.
_SAFE = re.compile(r"[^a-z0-9._@'-]")
MAX_PREFIX = 64


@router.get("/suggest", response_model=SuggestResponse)
async def suggest(
    request: Request,
    prefix: str = Query("", max_length=256, description="What the user has typed so far"),
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

    index = {"index": settings.emails_alias}
    response = await es.msearch(
        searches=[
            index,
            {
                "size": 0,
                # ``from`` is single-valued, so every bucket of the matches
                # starts with the prefix; no include pattern is needed.
                "query": {"prefix": {"from": cleaned}},
                "aggs": {"people": {"terms": {"field": "from", "size": size}}},
            },
            index,
            {
                "size": size,
                "query": {
                    "match_phrase_prefix": {
                        "subject": {"query": prefix[:MAX_PREFIX], "max_expansions": 20}
                    }
                },
                "_source": ["subject"],
            },
        ]
    )
    people, subjects = response["responses"]

    suggestions: list[Suggestion] = [
        Suggestion(value=str(b["key"]), kind="person", count=int(b["doc_count"]))
        for b in (people.get("aggregations") or {}).get("people", {}).get("buckets", [])
    ]

    seen: set[str] = set()
    for hit in (subjects.get("hits") or {}).get("hits", []):
        subject = str((hit.get("_source") or {}).get("subject") or "").strip()
        if subject and subject.lower() not in seen:
            seen.add(subject.lower())
            suggestions.append(Suggestion(value=subject, kind="subject"))

    return SuggestResponse(prefix=prefix, suggestions=suggestions[: size * 2], timings=_timings())
