"""Optional LLM-assisted pre-labelling for the conceptual queries.

Strictly a *suggestion* shown as the default in the labelling prompt -- the
human still decides, which is the point of the spec's "I will review the
judgments by hand". Off unless you pass --prelabel, because it spends API
credits and because an automatic suggestion anchors the reviewer.

Uses the Anthropic HTTP API through httpx, which the API service already
depends on, so this adds nothing to the dependency tree.
"""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from typing import Any

import httpx

API_URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2023-06-01"
DEFAULT_MODEL = "claude-sonnet-5"
TIMEOUT_S = 30.0

_RUBRIC = """You are grading search results for an email investigation tool.

Grade how well the email answers the investigator's need, 0-3:
3 = exactly what they were looking for
2 = clearly on topic and useful
1 = related but marginal
0 = irrelevant

Answer with a single digit and nothing else."""


class PrelabelUnavailable(RuntimeError):
    """Raised when pre-labelling was asked for but cannot run."""


def _prompt(query: Mapping[str, Any], doc: Mapping[str, Any]) -> str:
    body = " ".join(str(doc.get("body") or "").split())[:1200]
    return (
        f"Investigator's query: {query.get('query')}\n"
        f"What they want: {query.get('intent', '')}\n\n"
        f"Email\n"
        f"  from: {doc.get('from', '')}\n"
        f"  date: {str(doc.get('date') or '')[:10]}\n"
        f"  subject: {doc.get('subject', '')}\n"
        f"  body: {body}\n\n"
        f"Grade (0-3):"
    )


def suggest_grade(
    query: Mapping[str, Any],
    doc: Mapping[str, Any],
    *,
    model: str = DEFAULT_MODEL,
    client: httpx.Client | None = None,
) -> int | None:
    """Ask the model for a 0-3 grade. Returns None if it gave no usable answer."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        msg = "ANTHROPIC_API_KEY is not set; cannot pre-label"
        raise PrelabelUnavailable(msg)

    payload = {
        "model": model,
        "max_tokens": 8,
        "system": _RUBRIC,
        "messages": [{"role": "user", "content": _prompt(query, doc)}],
    }
    headers = {
        "x-api-key": api_key,
        "anthropic-version": API_VERSION,
        "content-type": "application/json",
    }

    owned = client is None
    http = client or httpx.Client(timeout=TIMEOUT_S)
    try:
        response = http.post(API_URL, json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()
    except httpx.HTTPError as exc:
        raise PrelabelUnavailable(f"pre-label request failed: {exc}") from exc
    finally:
        if owned:
            http.close()

    return parse_grade(data)


def parse_grade(data: Mapping[str, Any]) -> int | None:
    """Pull a 0-3 grade out of a Messages API response."""
    blocks = data.get("content") or []
    text = " ".join(str(block.get("text", "")) for block in blocks if isinstance(block, dict))
    match = re.search(r"[0-3]", text)
    return int(match.group()) if match else None
