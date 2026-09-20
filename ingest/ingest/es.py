"""Synchronous Elasticsearch client for the ingestion CLI."""

from __future__ import annotations

from elasticsearch import Elasticsearch

from ingest.config import IngestSettings, get_settings


def make_client(settings: IngestSettings | None = None) -> Elasticsearch:
    settings = settings or get_settings()
    return Elasticsearch(
        hosts=settings.es_hosts,
        basic_auth=(settings.es_username, settings.es_password),
        ca_certs=settings.es_ca_cert,
        request_timeout=settings.es_timeout,
    )
