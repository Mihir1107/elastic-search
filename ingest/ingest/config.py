"""Ingestion settings + data-directory layout, from environment / .env.

All ``data/`` paths are gitignored. Stages read/write staged JSONL under these
directories and emit stats JSON to ``stats_dir`` (see CLAUDE_CODE_KICKOFF.md §5).
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class IngestSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Elasticsearch.
    es_host: str = "https://localhost:9200"
    es_username: str = "elastic"
    es_password: str = Field(default="", validation_alias="ELASTIC_PASSWORD")
    es_ca_cert: str = "./certs/ca.crt"
    es_timeout: float = 60.0

    # Index / alias (write to a concrete version, flip the alias last).
    emails_alias: str = "emails"
    index_version: str = "v1"

    # Embeddings / chunking.
    embed_model: str = "BAAI/bge-small-en-v1.5"
    embed_dims: int = 384
    embed_batch_size: int = 64
    chunk_tokens: int = 200
    chunk_overlap: int = 40

    # Corpus source (verified live 2026-09-20; 443,254,787 bytes).
    enron_url: str = "https://www.cs.cmu.edu/~enron/enron_mail_20150507.tar.gz"
    enron_sha256: str = ""  # pinned in Phase 1 after the first verified download

    # Data layout.
    data_dir: Path = Path("data")
    dev_subset_size: int = 10_000

    @property
    def raw_dir(self) -> Path:
        return self.data_dir / "raw"

    @property
    def interim_dir(self) -> Path:
        return self.data_dir / "interim"

    @property
    def stats_dir(self) -> Path:
        return self.data_dir / "stats"

    @property
    def index_name(self) -> str:
        return f"{self.emails_alias}-{self.index_version}"


@lru_cache
def get_settings() -> IngestSettings:
    return IngestSettings()
