"""Application settings loaded from environment / .env.

Central config kills the prototype's hardcoded ``localhost:9200`` and disabled
security (kickoff flaw #7). Nothing here connects to Elasticsearch.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Elasticsearch connection (TLS + basic auth; see docker-compose.yml).
    es_host: str = "https://localhost:9200"
    es_username: str = "elastic"
    # Single source of truth for the superuser password is ELASTIC_PASSWORD.
    es_password: str = Field(default="", validation_alias="ELASTIC_PASSWORD")
    es_ca_cert: str = "./certs/ca.crt"
    es_timeout: float = 30.0

    # Index / models.
    emails_alias: str = "emails"
    embed_model: str = "BAAI/bge-small-en-v1.5"
    embed_dims: int = 384
    # BGE retrieval uses an instruction prefix on the QUERY side only.
    bge_query_prefix: str = "Represent this sentence for searching relevant passages: "
    rerank_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"

    # Search behaviour.
    default_page_size: int = 20
    max_page_size: int = 50
    #: How deep each retrieval leg goes before fusion. Manual RRF happens in the
    #: API, so this bounds both cost and how far pagination can walk.
    fusion_window: int = 200
    knn_num_candidates: int = 200
    #: Load the embedding model at startup so the first query is not slow.
    warm_model: bool = True


@lru_cache
def get_settings() -> Settings:
    return Settings()
