"""Request validation and access control that need no cluster."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.search.parser import MAX_PHRASES, parse


@pytest.fixture
def client() -> Iterator[TestClient]:
    """The real app, without its lifespan: no Elasticsearch is contacted."""
    from app.main import app

    app.state.settings = Settings(_env_file=None)  # type: ignore[call-arg]
    app.state.es = object()  # any use of it would raise: validation must come first
    try:
        yield TestClient(app, raise_server_exceptions=False)
    finally:
        del app.state.settings, app.state.es


def test_a_malformed_tag_filter_is_a_422_not_a_500(client: TestClient) -> None:
    for path in ("/search", "/export"):
        res = client.get(path, params={"q": "x", "tag": "Not Valid!"})
        assert res.status_code == 422, (path, res.text)


def test_filter_value_lists_are_bounded(client: TestClient) -> None:
    res = client.get("/search", params=[("q", "x"), *[("from", f"a{i}@b.com") for i in range(40)]])
    assert res.status_code == 422
    assert "from" in res.json()["detail"]


def test_batch_bodies_are_bounded(client: TestClient) -> None:
    res = client.post("/tags/batch", json={"ids": [str(i) for i in range(501)], "add": ["hot"]})
    assert res.status_code == 422


def test_docs_are_off_by_default(client: TestClient) -> None:
    assert client.get("/docs").status_code == 404
    assert client.get("/openapi.json").status_code == 404


def test_liveness_needs_nothing(client: TestClient) -> None:
    assert client.get("/livez").json() == {"status": "ok"}


def test_the_api_key_is_enforced_when_configured(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LEDGER_API_KEY", "k3y")
    get_settings.cache_clear()
    try:
        assert client.get("/tags").status_code == 401
        assert client.get("/tags", headers={"x-api-key": "wrong"}).status_code == 401
        assert client.get("/livez").status_code == 200
        # The right key gets past the gate (and on to the fake client, hence 500).
        assert client.get("/tags", headers={"x-api-key": "k3y"}).status_code != 401
    finally:
        get_settings.cache_clear()


def test_quoted_phrases_are_capped() -> None:
    q = parse(" ".join(f'"p{i} x"' for i in range(MAX_PHRASES + 3)))
    assert len(q.phrases) == MAX_PHRASES
    assert any("quoted phrases" in w for w in q.warnings)


def test_reviewer_header_is_sanitised() -> None:
    from starlette.requests import Request

    from app.routes.tags import reviewer

    scope = {"type": "http", "headers": [(b"x-ledger-user", b"ann\x07" + b"e" * 100)]}
    assert reviewer(Request(scope)) == ("ann" + "e" * 100)[:64]
