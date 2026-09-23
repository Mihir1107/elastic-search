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
    #: The API should not run as the superuser: `make api-user` creates a
    #: least-privilege user (read on the email indices, write on the tags index)
    #: and these two settings select it. Unset, it falls back to ``elastic``.
    es_api_username: str = Field(default="", validation_alias="ES_API_USERNAME")
    es_api_password: str = Field(default="", validation_alias="ES_API_PASSWORD")
    es_username: str = "elastic"
    # Single source of truth for the superuser password is ELASTIC_PASSWORD.
    es_password: str = Field(default="", validation_alias="ELASTIC_PASSWORD")
    es_ca_cert: str = "./certs/ca.crt"
    es_timeout: float = 30.0

    @property
    def es_hosts(self) -> list[str]:
        """``es_host`` split into the list the client is constructed with."""
        return [host.strip() for host in self.es_host.split(",") if host.strip()]

    @property
    def es_credentials(self) -> tuple[str, str]:
        """The least-privilege API user when configured, else the superuser."""
        if self.es_api_username:
            return self.es_api_username, self.es_api_password
        return self.es_username, self.es_password

    #: Shared secret required on every request (``X-API-Key``) when set. The web
    #: proxy adds it server-side, so the browser never sees it. Empty = open,
    #: which is only acceptable while the API listens on localhost.
    api_key: str = Field(default="", validation_alias="LEDGER_API_KEY")
    #: Serve /docs and /openapi.json. Off unless asked for: they map the whole
    #: attack surface for whoever can reach the port.
    expose_docs: bool = False

    # Index / models.
    emails_alias: str = "emails"
    #: Review tags, kept apart from the email index so a reindex cannot drop them (D37).
    tags_index: str = "ledger-tags"
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
    #: Embed the spelling-corrected free text rather than the raw typo (D35).
    spell_correct_embedding: bool = True
    #: ``minimum_should_match`` for the free-text clause (None = plain OR). Plain
    #: OR let "california power crisis" match anything containing "power", and
    #: the total and every facet counted that inflated set. "2<50%": one or two
    #: terms must all match, longer queries need half. Measured on the tune
    #: split, confirmed on test (D35); the stricter "2<75%" costs conceptual
    #: queries more than it gains.
    bm25_minimum_should_match: str | None = "2<50%"
    #: Load the embedding model at startup so the first query is not slow.
    warm_model: bool = True
    #: How many model forward passes (embed + rerank) may run at once. torch
    #: already uses several cores per pass; unbounded threads just thrash.
    model_concurrency: int = 2
    #: Fused candidate lists kept for pagination and export, and for how long.
    #: Page two of a search then costs only its hydration, not a full re-run.
    result_cache_size: int = 256
    result_cache_ttl_s: float = 300.0
    #: Query vectors kept, so re-running or paging a query skips the model.
    embed_cache_size: int = 1024
    #: Load the cross-encoder in a background thread at startup. Its first use
    #: otherwise costs ~8s (F19), which in the UI reads as a Rerank button that
    #: does nothing. Background, so it never delays the API becoming ready.
    warm_reranker: bool = True


@lru_cache
def get_settings() -> Settings:
    return Settings()
