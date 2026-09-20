"""Application settings loaded from environment / .env.

Central config kills the prototype's hardcoded ``localhost:9200`` and disabled
security (spec flaw #7). Nothing here connects to Elasticsearch.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Elasticsearch connection (TLS + basic auth; see docker-compose.yml).
    # Comma-separated: the client must hold every node it can reach, or killing
    # the one node it knows about fails every request (Phase 6's HA gate). The
    # client round-robins and retries a request on another node when one dies.
    # Ref: elastic.co/docs/reference/elasticsearch/clients/python/connecting
    es_host: str = "https://localhost:9200"
    es_username: str = "elastic"
    # Single source of truth for the superuser password is ELASTIC_PASSWORD.
    es_password: str = Field(default="", validation_alias="ELASTIC_PASSWORD")
    es_ca_cert: str = "./certs/ca.crt"
    es_timeout: float = 30.0

    @property
    def es_hosts(self) -> list[str]:
        """``es_host`` split into the list the client is constructed with."""
        return [host.strip() for host in self.es_host.split(",") if host.strip()]

    # Index / models.
    emails_alias: str = "emails"
    embed_model: str = "BAAI/bge-small-en-v1.5"
    embed_dims: int = 384
    # BGE retrieval uses an instruction prefix on the QUERY side only.
    bge_query_prefix: str = "Represent this sentence for searching relevant passages: "
    rerank_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    #: Reranking is off unless a request asks for it; this flips the default.
    rerank_enabled: bool = False
    #: Only rerank queries that are pure free text. When the user supplied an
    #: explicit precision signal -- a quoted phrase or a from:/to:/date operator --
    #: that intent should not be overridden by a semantic reranker. Measured:
    #: see eval/results/ and DECISIONS D23.
    rerank_free_text_only: bool = True
    #: How many fused results the cross-encoder rescores (spec: top 50).
    rerank_window: int = 50
    #: BM25 field boosts, configurable so tuning sweeps need no code change.
    #: Tuned in Phase 4. The spec prescribed subject^3; measured on the judged
    #: set that is too aggressive, and the effect is monotone: ^5 -0.020,
    #: ^3 baseline, ^2 +0.017, ^1 +0.021 NDCG@10 (and ^1 is +0.060 MRR). The
    #: best-measured value wins rather than a theoretical preference for boosting
    #: subject; see DECISIONS D24 for the caveat this carries.
    bm25_fields: list[str] = ["subject", "body", "from.text", "to.text"]

    # Search behaviour.
    default_page_size: int = 20
    max_page_size: int = 50
    #: How deep each retrieval leg goes before fusion. Manual RRF happens in the
    #: API, so this bounds both cost and how far pagination can walk.
    #: Candidates fetched per leg, and the depth pagination can reach. Constant
    #: per query: RRF ranks a document against whatever it was fused with, so a
    #: window that grew with the page made page two repeat page one (D32).
    #: 120 measured best against the 300ms p95 target once highlighting moved
    #: off this query: p95 220.5ms at concurrency 4 versus 294.9ms at 200.
    fusion_window: int = 120
    knn_num_candidates: int = 200
    #: Load the embedding model at startup so the first query is not slow.
    warm_model: bool = True


@lru_cache
def get_settings() -> Settings:
    return Settings()
