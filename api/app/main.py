"""Ledger search API.

Phase 0 exposes only a liveness ``/health`` stub that does NOT touch
Elasticsearch, so unit tests run offline. Cluster health, license-tier logging,
the native-RRF probe, and the real search endpoints arrive in Phase 2
(see CLAUDE_CODE_KICKOFF.md sections 4 and 6).
"""

from __future__ import annotations

from fastapi import FastAPI

app = FastAPI(title="Ledger Search API", version="0.0.0")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "phase": "0"}
