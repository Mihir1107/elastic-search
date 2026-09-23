"""Review tags: the reviewer's work product, kept apart from the evidence.

Tags live in their own index, one document per tagged email, keyed by the
email's id. Not on the email documents themselves: ingest builds a fresh index
version and swaps the alias on every reindex, which would silently discard
every tag, and the corpus should read the same whoever has been reviewing it.
Email ids are content hashes (ingest stage 4), so a tag survives a reindex of
the same mail. DECISIONS D37.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime
from typing import Any

from elasticsearch import AsyncElasticsearch, NotFoundError
from elasticsearch.helpers import async_bulk

TAG_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{0,31}$")
MAX_TAGS_PER_EMAIL = 16
#: Emails one batch request may touch.
MAX_BATCH = 500
#: A tag filter resolves to an ids filter; beyond this it is truncated, and says
#: so. 10,000 is also Elasticsearch's default max_result_window, the most one
#: search may return.
MAX_FILTER_IDS = 10_000

_MAPPING: dict[str, Any] = {
    "mappings": {
        "dynamic": "strict",
        "properties": {
            "tags": {"type": "keyword"},
            "updated_at": {"type": "date"},
            #: Who made the last change: the reviewer the web tier authenticated.
            "updated_by": {"type": "keyword"},
        },
    }
}

#: Indices already checked by this process; checking costs a round trip.
_ready: set[str] = set()

#: Bumped on every tag write. Cached search results that filtered by tag are
#: keyed on it, so a change is never hidden behind a stale page.
_generation = 0


def generation() -> int:
    return _generation


def _changed() -> None:
    global _generation
    _generation += 1


#: Add then remove, and drop the document once nothing is left on it, so the
#: index only ever holds emails that actually carry a tag.
_BATCH_SCRIPT = """
if (ctx._source.tags == null) { ctx._source.tags = []; }
for (t in params.add) { if (!ctx._source.tags.contains(t)) { ctx._source.tags.add(t); } }
ctx._source.tags.removeIf(t -> params.remove.contains(t));
if (ctx._source.tags.size() > params.max) { ctx.op = 'none'; }
else if (ctx._source.tags.isEmpty()) { ctx.op = 'delete'; }
else { ctx._source.updated_at = params.now; ctx._source.updated_by = params.by; }
"""


class TagError(ValueError):
    """A tag name or request that cannot be accepted."""


def normalise_tags(tags: Iterable[str]) -> list[str]:
    """Lowercase, trim, validate and de-duplicate; sorted for stable output."""
    out: set[str] = set()
    for raw in tags:
        tag = str(raw).strip().lower()
        if not TAG_PATTERN.match(tag):
            msg = f"invalid tag {raw!r}: use 1-32 of a-z, 0-9 and '-', starting alphanumeric"
            raise TagError(msg)
        out.add(tag)
    if len(out) > MAX_TAGS_PER_EMAIL:
        msg = f"at most {MAX_TAGS_PER_EMAIL} tags per email"
        raise TagError(msg)
    return sorted(out)


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _script_params(add: list[str], remove: list[str], now: str, by: str) -> dict[str, Any]:
    """Parameters for ``_BATCH_SCRIPT``; ``max`` makes an over-full email a no-op."""
    return {"add": add, "remove": remove, "now": now, "by": by, "max": MAX_TAGS_PER_EMAIL}


async def ensure_index(es: AsyncElasticsearch, index: str) -> None:
    """Create the tags index, or add any field an older one lacks. Once per process."""
    if index in _ready:
        return
    if not await es.indices.exists(index=index):
        await es.options(ignore_status=400).indices.create(index=index, **_MAPPING)
    else:
        # Additive only (a new field), so safe on an index that already holds tags.
        await es.indices.put_mapping(index=index, properties=_MAPPING["mappings"]["properties"])
    _ready.add(index)


def reset_ready() -> None:
    """Test hook: forget which indices were prepared."""
    _ready.clear()


async def get_tags(
    es: AsyncElasticsearch, index: str, email_ids: Sequence[str]
) -> dict[str, list[str]]:
    """Tags for each id that has any; untagged ids are simply absent."""
    if not email_ids:
        return {}
    try:
        response = await es.mget(index=index, ids=list(email_ids), source_includes=["tags"])
    except NotFoundError:  # nothing has been tagged yet: no index
        return {}
    return {
        doc["_id"]: sorted(doc["_source"].get("tags") or [])
        for doc in response["docs"]
        if doc.get("found")
    }


async def set_tags(
    es: AsyncElasticsearch, index: str, email_id: str, tags: Sequence[str], by: str = ""
) -> list[str]:
    """Replace an email's tags. An empty list removes the email from the index.

    Last write wins, by definition of "replace". Interactive clients should use
    :func:`change_tags`, which cannot lose a concurrent reviewer's edit.
    """
    clean = normalise_tags(tags)
    await ensure_index(es, index)
    if clean:
        await es.index(
            index=index,
            id=email_id,
            document={"tags": clean, "updated_at": _now(), "updated_by": by},
            refresh="wait_for",
        )
    else:
        await es.options(ignore_status=404).delete(index=index, id=email_id, refresh="wait_for")
    _changed()
    return clean


async def change_tags(
    es: AsyncElasticsearch,
    index: str,
    email_id: str,
    add: Sequence[str],
    remove: Sequence[str],
    by: str = "",
) -> list[str]:
    """Add and remove tags on one email atomically; returns the tags it now has.

    The change is applied inside Elasticsearch by the same script as a batch,
    so two reviewers tagging the same email at once both keep their edit --
    unlike a read-modify-replace from the client, where the second overwrites
    the first.
    """
    add_clean, remove_clean = normalise_tags(add), normalise_tags(remove)
    if not (add_clean or remove_clean):
        return (await get_tags(es, index, [email_id])).get(email_id, [])
    await ensure_index(es, index)
    now = _now()
    body: dict[str, Any] = {
        "script": {
            "source": _BATCH_SCRIPT,
            "lang": "painless",
            "params": _script_params(add_clean, remove_clean, now, by),
        },
    }
    if first := [t for t in add_clean if t not in remove_clean]:
        body["upsert"] = {"tags": first, "updated_at": now, "updated_by": by}
    response = await es.options(ignore_status=404).update(
        index=index,
        id=email_id,
        refresh="wait_for",
        source=True,
        retry_on_conflict=3,
        **body,
    )
    _changed()
    # 404: only removals, on an email that had no tags. "deleted": the script
    # removed the last tag and dropped the document.
    if response.meta.status == 404 or response.get("result") == "deleted":
        return []
    source = (response.get("get") or {}).get("_source") or {}
    return sorted(source.get("tags") or add_clean)


async def batch_tags(
    es: AsyncElasticsearch,
    index: str,
    email_ids: Sequence[str],
    add: Sequence[str],
    remove: Sequence[str],
    by: str = "",
) -> int:
    """Add and remove tags across many emails at once; returns how many changed."""
    add_clean, remove_clean = normalise_tags(add), normalise_tags(remove)
    ids = list(dict.fromkeys(email_ids))
    if len(ids) > MAX_BATCH:
        msg = f"at most {MAX_BATCH} emails per batch"
        raise TagError(msg)
    if not ids or not (add_clean or remove_clean):
        return 0
    await ensure_index(es, index)
    params = _script_params(add_clean, remove_clean, _now(), by)
    first = [t for t in add_clean if t not in remove_clean]
    actions: list[dict[str, Any]] = []
    for email_id in ids:
        action: dict[str, Any] = {
            "_op_type": "update",
            "_index": index,
            "_id": email_id,
            "script": {"source": _BATCH_SCRIPT, "lang": "painless", "params": params},
        }
        if first:
            # A first tag creates the document; removal from an untagged email
            # is a no-op, reported by ES as document_missing and ignored below.
            action["upsert"] = {"tags": first, "updated_at": params["now"], "updated_by": by}
        actions.append(action)
    ok, errors = await async_bulk(
        es, actions, raise_on_error=False, raise_on_exception=False, refresh="wait_for"
    )
    _changed()
    error_list: list[dict[str, Any]] = errors if isinstance(errors, list) else []
    failures = [e for e in error_list if (e.get("update") or {}).get("status") != 404]
    if failures:
        msg = f"{len(failures)} tag update(s) failed: {failures[0]}"
        raise RuntimeError(msg)
    return int(ok)


async def ids_with_tags(
    es: AsyncElasticsearch, index: str, tags: Sequence[str]
) -> tuple[list[str], bool]:
    """Ids of emails carrying any of ``tags``, and whether the list was truncated."""
    try:
        response = await es.search(
            index=index,
            query={"terms": {"tags": normalise_tags(tags)}},
            size=MAX_FILTER_IDS,
            source=False,
            sort=["_doc"],
            track_total_hits=True,
        )
    except NotFoundError:
        return [], False
    ids = [hit["_id"] for hit in response["hits"]["hits"]]
    return ids, int(response["hits"]["total"]["value"]) > len(ids)


async def tag_counts(es: AsyncElasticsearch, index: str) -> list[dict[str, Any]]:
    """Every tag in use with the number of emails carrying it, most used first."""
    try:
        response = await es.search(
            index=index, size=0, aggs={"tags": {"terms": {"field": "tags", "size": 200}}}
        )
    except NotFoundError:
        return []
    buckets = response["aggregations"]["tags"]["buckets"]
    return [{"tag": b["key"], "count": b["doc_count"]} for b in buckets]
