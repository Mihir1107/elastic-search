"""Ledger search API.

On startup the app reports the Elasticsearch version and the license tier, and
empirically probes whether the native ``rrf`` retriever is usable on this
cluster. Fusion always uses manual RRF regardless of the answer -- the probe
exists so the licensing question is settled by observation and visible in the
logs, never depended upon (kickoff section 4, DECISIONS D1).
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import get_settings
from app.es import make_client
from app.probe import get_license_tier, probe_native_rrf
from app.routes import emails, health, search, suggest, threads

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("ledger.api")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    es = make_client(settings)
    app.state.settings = settings
    app.state.es = es

    try:
        info = await es.info()
        logger.info(
            "connected to elasticsearch %s (cluster %s)",
            info["version"]["number"],
            info["cluster_name"],
        )
    except Exception as exc:
        logger.warning("could not reach elasticsearch at startup: %s", exc)

    tier = await get_license_tier(es)
    app.state.license_tier = tier
    logger.info("elasticsearch license tier: %s", tier)
    if tier not in {"basic", "trial"}:
        logger.warning("license tier %r is not Basic; this product targets Basic", tier)

    app.state.native_rrf_available = await probe_native_rrf(es, settings.emails_alias)

    if settings.warm_model:
        try:
            from app.search.embedder import get_model

            get_model(settings.embed_model)
            logger.info("embedding model warm: %s", settings.embed_model)
        except Exception as exc:
            logger.warning("could not warm the embedding model: %s", exc)

    try:
        yield
    finally:
        await es.close()


app = FastAPI(
    title="Ledger Search API",
    version="0.2.0",
    summary="Email investigation search over the Enron corpus",
    lifespan=lifespan,
)

app.include_router(health.router)
app.include_router(search.router)
app.include_router(emails.router)
app.include_router(threads.router)
app.include_router(suggest.router)
