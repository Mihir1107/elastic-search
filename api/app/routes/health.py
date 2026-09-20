"""GET /health -- API + cluster health, license tier, active index version."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Request

from app.config import get_settings
from app.models import HealthResponse

router = APIRouter(tags=["health"])
logger = logging.getLogger(__name__)


@router.get("/health", response_model=HealthResponse)
async def health(request: Request) -> HealthResponse:
    # Health must report, never raise -- including before/without the lifespan
    # having populated app.state (e.g. a bare TestClient, or a failed startup).
    state = request.app.state
    settings = getattr(state, "settings", None) or get_settings()
    response = HealthResponse(
        status="ok",
        alias=settings.emails_alias,
        license_tier=getattr(state, "license_tier", None),
        native_rrf_available=getattr(state, "native_rrf_available", None),
    )
    try:
        es = getattr(state, "es", None)
        if es is None:
            raise RuntimeError("elasticsearch client not initialised")
        cluster = await es.cluster.health()
        response.elasticsearch = str(cluster["status"])
        response.cluster_name = str(cluster["cluster_name"])
        response.number_of_nodes = int(cluster["number_of_nodes"])
        response.active_shards = int(cluster.get("active_shards", 0))
        aliases = await es.indices.get_alias(name=settings.emails_alias)
        response.active_index = sorted(aliases.keys())
        counted = await es.count(index=settings.emails_alias)
        response.docs = int(counted["count"])
        if response.elasticsearch == "red" or not response.active_index:
            response.status = "degraded"
    except Exception as exc:
        logger.warning("health check could not reach Elasticsearch: %s", exc)
        response.status = "degraded"
        response.detail = f"elasticsearch unreachable: {type(exc).__name__}"
    return response
