"""Startup license checks.

The spec requires the API to report the license tier at startup and to never
depend on a paid feature. We fuse with manual RRF regardless (DECISIONS D1), but
we also *empirically* ask this cluster whether the native ``rrf`` retriever is
usable, so the ambiguity in the docs is settled by observation and recorded in
the logs rather than guessed at.
"""

from __future__ import annotations

import logging

from elasticsearch import AsyncElasticsearch

logger = logging.getLogger(__name__)


async def get_license_tier(es: AsyncElasticsearch) -> str:
    try:
        response = await es.license.get()
        return str(response["license"]["type"])
    except Exception as exc:
        logger.warning("could not read license tier: %s", exc)
        return "unknown"


async def probe_native_rrf(es: AsyncElasticsearch, index: str) -> bool:
    """Return True if the native rrf retriever runs on this cluster/license."""
    body = {
        "retriever": {
            "rrf": {
                "retrievers": [
                    {"standard": {"query": {"match_all": {}}}},
                    {"standard": {"query": {"match_all": {}}}},
                ],
                "rank_window_size": 2,
            }
        },
        "size": 1,
    }
    try:
        await es.search(index=index, body=body)
    except Exception as exc:
        logger.info("native rrf retriever unavailable (%s); using manual RRF", type(exc).__name__)
        return False
    logger.info("native rrf retriever IS available; still using manual RRF (DECISIONS D1)")
    return True
