"""Async Elasticsearch client factory. No connection is made at import time."""

from __future__ import annotations

from elasticsearch import AsyncElasticsearch

from app.config import Settings, get_settings


def make_client(settings: Settings | None = None) -> AsyncElasticsearch:
    settings = settings or get_settings()
    return AsyncElasticsearch(
        hosts=settings.es_hosts,
        basic_auth=settings.es_credentials,
        ca_certs=settings.es_ca_cert,
        request_timeout=settings.es_timeout,
    )
