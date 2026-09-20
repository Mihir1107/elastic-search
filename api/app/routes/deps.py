"""Shared request dependencies."""

from __future__ import annotations

from elasticsearch import AsyncElasticsearch
from fastapi import Request

from app.config import Settings


def get_es(request: Request) -> AsyncElasticsearch:
    client: AsyncElasticsearch = request.app.state.es
    return client


def get_settings_from(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings
