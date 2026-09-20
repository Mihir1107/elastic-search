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


def test_es_hosts_splits_a_comma_separated_list() -> None:
    """The HA gate needs every node in the client, not just the first: killing
    the one node the client knows about would fail every request."""
    s = Settings(
        _env_file=None,  # type: ignore[call-arg]
        es_host="https://localhost:9200, https://localhost:9201,https://localhost:9202",
    )
    assert s.es_hosts == [
        "https://localhost:9200",
        "https://localhost:9201",
        "https://localhost:9202",
    ]


def test_es_hosts_is_a_single_element_list_for_one_host() -> None:
    s = Settings(_env_file=None, es_host="https://localhost:9200")  # type: ignore[call-arg]
    assert s.es_hosts == ["https://localhost:9200"]


def test_es_hosts_drops_empty_entries() -> None:
    s = Settings(_env_file=None, es_host="https://a:9200,,  ,https://b:9200")  # type: ignore[call-arg]
    assert s.es_hosts == ["https://a:9200", "https://b:9200"]
