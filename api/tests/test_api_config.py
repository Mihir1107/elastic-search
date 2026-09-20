from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import app


def test_settings_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ELASTIC_PASSWORD", raising=False)
    s = Settings(_env_file=None)  # type: ignore[call-arg]
    assert s.es_host.startswith("https://")
    assert s.embed_dims == 384
    assert s.emails_alias == "emails"


def test_password_comes_from_elastic_password(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ELASTIC_PASSWORD", "s3cret")
    s = Settings(_env_file=None)  # type: ignore[call-arg]
    assert s.es_password == "s3cret"


def test_health_never_raises_without_a_lifespan() -> None:
    """A bare client skips startup, so app.state is empty: report, do not 500."""
    client = TestClient(app)
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "degraded"
    assert body["api"] == "ok"
    assert "elasticsearch" in (body["detail"] or "")
