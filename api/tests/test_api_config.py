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


def test_health_endpoint() -> None:
    client = TestClient(app)
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
