"""Ledger search API.

On startup the app reports the Elasticsearch version and the license tier, and
empirically probes whether the native ``rrf`` retriever is usable on this
cluster. Fusion always uses manual RRF regardless of the answer -- the probe
exists so the licensing question is settled by observation and visible in the
logs, never depended upon (docs/SPEC.md section 3, DECISIONS D1).
"""

from __future__ import annotations

import asyncio
import hmac
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from elasticsearch import BadRequestError
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.es import make_client
from app.probe import get_license_tier, probe_native_rrf
from app.routes import emails, export, health, search, suggest, tags, threads
from app.search.embedder import configure_cache as configure_vector_cache
from app.search.embedder import configure_gate
from app.search.service import configure_cache as configure_result_cache
from app.tags import TagError, ensure_index

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("ledger.api")


async def _warm_reranker(name: str) -> None:
    try:
        from app.search.rerank import get_reranker

        await asyncio.to_thread(get_reranker, name)
        logger.info("reranker warm: %s", name)
    except Exception as exc:
        logger.warning("could not warm the reranker: %s", exc)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_gate(settings.model_concurrency)
    configure_vector_cache(settings.embed_cache_size)
    configure_result_cache(settings.result_cache_size, settings.result_cache_ttl_s)
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

    try:
        # Once here rather than before every tag write.
        await ensure_index(es, settings.tags_index)
    except Exception as exc:
        logger.warning("could not prepare the tags index %s: %s", settings.tags_index, exc)

    if settings.warm_model:
        try:
            from app.search.embedder import get_model

            get_model(settings.embed_model)
            logger.info("embedding model warm: %s", settings.embed_model)
        except Exception as exc:
            logger.warning("could not warm the embedding model: %s", exc)

    if settings.warm_reranker:
        # Not awaited: the API is ready before the cross-encoder is. A request
        # that arrives first simply waits on the loader's lock, as it did before.
        app.state.reranker_warmup = asyncio.create_task(_warm_reranker(settings.rerank_model))

    try:
        yield
    finally:
        await es.close()


_settings = get_settings()
app = FastAPI(
    title="Ledger Search API",
    version="0.3.0",
    summary="Email investigation search over the Enron corpus",
    lifespan=lifespan,
    docs_url="/docs" if _settings.expose_docs else None,
    redoc_url=None,
    openapi_url="/openapi.json" if _settings.expose_docs else None,
)

#: Answers the liveness probe without a key, so an orchestrator can check the
#: process without holding the secret. It reports nothing about the cluster.
_OPEN_PATHS = frozenset({"/livez"})


@app.middleware("http")
async def require_api_key(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    expected = get_settings().api_key
    if expected and request.url.path not in _OPEN_PATHS:
        supplied = request.headers.get("x-api-key", "")
        if not hmac.compare_digest(supplied.encode(), expected.encode()):
            return JSONResponse({"detail": "missing or invalid API key"}, status_code=401)
    return await call_next(request)


@app.exception_handler(TagError)
async def tag_error(_: Request, exc: TagError) -> JSONResponse:
    """A bad tag anywhere -- a filter, a write -- is the caller's mistake, not a 500."""
    return JSONResponse({"detail": str(exc)}, status_code=422)


@app.exception_handler(BadRequestError)
async def es_bad_request(_: Request, exc: BadRequestError) -> JSONResponse:
    """Elasticsearch refused the request (e.g. too many clauses): say so as a 400."""
    logger.warning("elasticsearch rejected a request: %s", exc)
    return JSONResponse({"detail": "the search could not be run as given"}, status_code=400)


app.include_router(health.router)
app.include_router(tags.router)
app.include_router(export.router)
app.include_router(search.router)
app.include_router(emails.router)
app.include_router(threads.router)
app.include_router(suggest.router)
