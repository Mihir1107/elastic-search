"""Response models for the v1 API."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class Facet(BaseModel):
    key: Any
    count: int


class Timings(BaseModel):
    """Per-stage latency. Every response carries one (docs/SPEC.md section 5)."""

    parse_ms: float = 0.0
    embed_ms: float = 0.0
    bm25_ms: float = 0.0
    knn_ms: float = 0.0
    fuse_ms: float = 0.0
    highlight_ms: float = 0.0
    rerank_ms: float = 0.0
    total_ms: float = 0.0


class Correction(BaseModel):
    original: str
    suggested: str


class Understood(BaseModel):
    """How the query was interpreted -- shown so the behaviour is explainable."""

    terms: list[str] = []
    phrases: list[str] = []
    from_: list[str] = Field(default=[], alias="from")
    to: list[str] = []
    cc: list[str] = []
    subject: list[str] = []
    after: str | None = None
    before: str | None = None
    #: Misspellings corrected before the query text was embedded.
    corrections: list[Correction] = []
    model_config = ConfigDict(populate_by_name=True)


class SearchHit(BaseModel):
    id: str
    score: float
    subject: str = ""
    from_: str = Field(default="", alias="from")
    from_name: str = ""
    to: list[str] = []
    cc: list[str] = []
    date: str | None = None
    thread_id: str | None = None
    mailboxes: list[str] = []
    folder: list[str] = []
    has_attachment: bool = False
    duplicate_count: int = 1
    snippets: list[str] = []
    matched_by: list[str] = []
    message_id: str = ""
    attachment_names: list[str] = []
    #: 1-based position within each retrieval leg, or None if that leg missed it.
    bm25_rank: int | None = None
    vector_rank: int | None = None
    model_config = ConfigDict(populate_by_name=True)


class SearchResponse(BaseModel):
    query: str
    understood: Understood
    total: int
    size: int
    hits: list[SearchHit]
    facets: dict[str, list[Facet]] = {}
    timings: Timings
    warnings: list[str] = []
    next_page_token: str | None = None
    reranked: bool = False


class EmailDetail(BaseModel):
    id: str
    message_id: str = ""
    thread_id: str | None = None
    subject: str = ""
    from_: str = Field(default="", alias="from")
    from_name: str = ""
    to: list[str] = []
    cc: list[str] = []
    bcc: list[str] = []
    date: str | None = None
    body: str = ""
    quoted_text: str = ""
    mailboxes: list[str] = []
    folder: list[str] = []
    has_attachment: bool = False
    attachment_names: list[str] = []
    duplicate_count: int = 1
    model_config = ConfigDict(populate_by_name=True)


class ThreadResponse(BaseModel):
    thread_id: str
    total: int
    messages: list[EmailDetail]
    timings: Timings


class Suggestion(BaseModel):
    value: str
    kind: str
    count: int | None = None


class SuggestResponse(BaseModel):
    prefix: str
    suggestions: list[Suggestion]
    timings: Timings


class HealthResponse(BaseModel):
    status: str
    api: str = "ok"
    elasticsearch: str | None = None
    cluster_name: str | None = None
    number_of_nodes: int | None = None
    license_tier: str | None = None
    native_rrf_available: bool | None = None
    active_index: list[str] = []
    alias: str = "emails"
    active_shards: int | None = None
    docs: int | None = None
    detail: str | None = None
