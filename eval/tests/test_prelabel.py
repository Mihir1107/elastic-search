"""Tests for LLM pre-labelling. No network and no API credits are used."""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from eval.prelabel import PrelabelUnavailable, parse_grade, suggest_grade

QUERY: dict[str, Any] = {"query": "concerns about hiding losses", "intent": "cover-ups"}
DOC: dict[str, Any] = {
    "from": "a@enron.com",
    "date": "2001-10-26",
    "subject": "Unplanned losses",
    "body": "the write-down was not disclosed",
}


def _client(handler: Any) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_parse_grade_reads_the_first_digit() -> None:
    assert parse_grade({"content": [{"type": "text", "text": "3"}]}) == 3
    assert parse_grade({"content": [{"type": "text", "text": "Grade: 2."}]}) == 2


def test_parse_grade_returns_none_without_a_usable_answer() -> None:
    assert parse_grade({"content": [{"type": "text", "text": "not sure"}]}) is None
    assert parse_grade({"content": []}) is None
    assert parse_grade({}) is None


def test_parse_grade_ignores_out_of_range_digits() -> None:
    assert parse_grade({"content": [{"type": "text", "text": "9"}]}) is None


def test_missing_api_key_raises_clearly(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(PrelabelUnavailable, match="ANTHROPIC_API_KEY"):
        suggest_grade(QUERY, DOC)


def test_suggest_grade_sends_a_well_formed_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["headers"] = dict(request.headers)
        seen["url"] = str(request.url)
        import json as _json

        seen["body"] = _json.loads(request.content)
        return httpx.Response(200, json={"content": [{"type": "text", "text": "3"}]})

    with _client(handler) as client:
        assert suggest_grade(QUERY, DOC, client=client) == 3

    assert seen["url"].endswith("/v1/messages")
    assert seen["headers"]["x-api-key"] == "test-key"
    assert seen["headers"]["anthropic-version"]
    # the prompt must carry both the need and the document
    prompt = seen["body"]["messages"][0]["content"]
    assert "hiding losses" in prompt and "Unplanned losses" in prompt
    assert seen["body"]["max_tokens"] <= 16


def test_http_errors_surface_as_prelabel_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": "rate limited"})

    with _client(handler) as client, pytest.raises(PrelabelUnavailable):
        suggest_grade(QUERY, DOC, client=client)


def test_unparseable_answer_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"content": [{"type": "text", "text": "dunno"}]})

    with _client(handler) as client:
        assert suggest_grade(QUERY, DOC, client=client) is None
