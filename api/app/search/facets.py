"""Facet aggregations (kickoff flaw #3: the prototype had none)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

FACET_SIZE = 10


def build_aggs(size: int = FACET_SIZE) -> dict[str, Any]:
    return {
        "top_senders": {"terms": {"field": "from", "size": size}},
        "top_recipients": {"terms": {"field": "to", "size": size}},
        "folders": {"terms": {"field": "folder", "size": size}},
        "mailboxes": {"terms": {"field": "mailboxes", "size": size}},
        "has_attachment": {"terms": {"field": "has_attachment", "size": 2}},
        "over_time": {
            "date_histogram": {
                "field": "date",
                "calendar_interval": "month",
                "min_doc_count": 1,
            }
        },
    }


def parse_aggs(response: Mapping[str, Any]) -> dict[str, list[dict[str, Any]]]:
    aggs = response.get("aggregations") or {}
    facets: dict[str, list[dict[str, Any]]] = {}
    for name, payload in aggs.items():
        buckets = payload.get("buckets", [])
        facets[name] = [
            {
                "key": bucket.get("key_as_string", bucket.get("key")),
                "count": bucket.get("doc_count", 0),
            }
            for bucket in buckets
        ]
    return facets
