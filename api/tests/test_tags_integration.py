"""Review tags and export, end to end against the live cluster.

The app is pointed at a throwaway tags index for the module, so these tests
never touch real review work, and the index is deleted afterwards.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.integration

TEST_TAGS_INDEX = "ledger-tags-test"


@pytest.fixture(scope="module")
def client() -> Iterator[TestClient]:
    from app.main import app

    with TestClient(app) as test_client:
        if test_client.get("/health").json().get("status") != "ok":
            pytest.skip("cluster not ready")
        settings = app.state.settings
        app.state.settings = settings.model_copy(update={"tags_index": TEST_TAGS_INDEX})
        es = app.state.es
        test_client.portal.call(_drop, es)  # type: ignore[union-attr]
        try:
            yield test_client
        finally:
            test_client.portal.call(_drop, es)  # type: ignore[union-attr]
            app.state.settings = settings


async def _drop(es: Any) -> None:
    await es.options(ignore_status=404).indices.delete(index=TEST_TAGS_INDEX)


def _ids(client: TestClient, q: str, n: int) -> list[str]:
    hits = client.get("/search", params={"q": q, "size": n}).json()["hits"]
    assert len(hits) == n
    return [h["id"] for h in hits]


def _csv(text: str) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(text)))


def test_setting_tags_round_trips_through_detail_and_search(client: TestClient) -> None:
    (email_id,) = _ids(client, "california energy crisis", 1)
    res = client.put(f"/emails/{email_id}/tags", json={"tags": ["Hot", "relevant", "hot"]})
    assert res.status_code == 200
    assert res.json() == {"id": email_id, "tags": ["hot", "relevant"]}
    assert client.get(f"/emails/{email_id}").json()["tags"] == ["hot", "relevant"]

    hits = client.get("/search", params={"q": "california energy crisis", "size": 5}).json()["hits"]
    assert next(h for h in hits if h["id"] == email_id)["tags"] == ["hot", "relevant"]

    assert client.put(f"/emails/{email_id}/tags", json={"tags": []}).json()["tags"] == []
    assert client.get(f"/emails/{email_id}").json()["tags"] == []


def test_invalid_tags_and_unknown_emails_are_rejected(client: TestClient) -> None:
    (email_id,) = _ids(client, "gas", 1)
    assert client.put(f"/emails/{email_id}/tags", json={"tags": ["no spaces"]}).status_code == 422
    assert client.put("/emails/does-not-exist/tags", json={"tags": ["hot"]}).status_code == 404


def test_batch_tagging_then_filtering_and_counting_by_tag(client: TestClient) -> None:
    ids = _ids(client, "power outage", 5)
    res = client.post("/tags/batch", json={"ids": [*ids, "not-an-email"], "add": ["privileged"]})
    assert res.json() == {"updated": 5}

    body = client.get("/search", params={"q": "", "tag": "privileged", "size": 50}).json()
    assert {h["id"] for h in body["hits"]} == set(ids)
    assert body["total"] == 5
    counts = {t["tag"]: t["count"] for t in client.get("/tags").json()["tags"]}
    assert counts["privileged"] == 5

    client.post("/tags/batch", json={"ids": ids[:2], "remove": ["privileged"]})
    body = client.get("/search", params={"q": "", "tag": "privileged", "size": 50}).json()
    assert {h["id"] for h in body["hits"]} == set(ids[2:])


def test_a_tag_nobody_used_matches_nothing(client: TestClient) -> None:
    body = client.get("/search", params={"q": "gas", "tag": "never-used"}).json()
    assert body["total"] == 0 and body["hits"] == []


def test_export_of_a_filter_query_is_the_complete_set(client: TestClient) -> None:
    ids = _ids(client, "credit rating", 3)
    client.post("/tags/batch", json={"ids": ids, "add": ["export-me"]})
    res = client.get("/export", params={"tag": "export-me"})
    assert res.status_code == 200
    assert res.headers["x-ledger-export-mode"] == "complete"
    assert res.headers["x-ledger-export-truncated"] == "false"
    assert "attachment" in res.headers["content-disposition"]
    rows = _csv(res.text)
    assert {r["id"] for r in rows} == set(ids)
    assert all(r["tags"] == "export-me" for r in rows)


def test_export_of_a_text_query_is_the_ranked_list_in_order(client: TestClient) -> None:
    q = "gas pipeline capacity"
    shown = [h["id"] for h in client.get("/search", params={"q": q, "size": 20}).json()["hits"]]
    res = client.get("/export", params={"q": q})
    assert res.headers["x-ledger-export-mode"] == "ranked"
    rows = _csv(res.text)
    assert [r["id"] for r in rows[:20]] == shown
    assert [int(r["rank"]) for r in rows] == list(range(1, len(rows) + 1))


def test_atomic_changes_keep_a_concurrent_reviewers_edit(client: TestClient) -> None:
    """Two reviewers editing one email: both edits survive, unlike a replace."""
    email_id = _ids(client, "enron stock price", 1)[0]
    a = client.patch(
        f"/emails/{email_id}/tags", json={"add": ["hot"]}, headers={"x-ledger-user": "ann"}
    )
    b = client.patch(f"/emails/{email_id}/tags", json={"add": ["relevant"]})
    assert a.json()["tags"] == ["hot"]
    assert b.json()["tags"] == ["hot", "relevant"]
    assert client.get(f"/emails/{email_id}").json()["tags"] == ["hot", "relevant"]
    gone = client.patch(f"/emails/{email_id}/tags", json={"remove": ["hot", "relevant"]})
    assert gone.json()["tags"] == []
    # Removing from an untagged email is a no-op, not an error.
    assert client.patch(f"/emails/{email_id}/tags", json={"remove": ["hot"]}).json()["tags"] == []


def test_a_tag_change_is_seen_by_the_next_page_of_a_tag_filter(client: TestClient) -> None:
    """Cached pages are keyed on the tag generation, so a write invalidates them."""
    ids = _ids(client, "natural gas storage", 3)
    client.post("/tags/batch", json={"ids": ids[:1], "add": ["cache-check"]})
    first = client.get("/search", params={"tag": "cache-check", "size": 1}).json()
    assert first["total"] == 1
    client.post("/tags/batch", json={"ids": ids, "add": ["cache-check"]})
    again = client.get("/search", params={"tag": "cache-check", "size": 1}).json()
    assert again["total"] == 3
    token = again["next_page_token"]
    page_two = client.get("/search", params={"tag": "cache-check", "size": 1, "page_token": token})
    assert page_two.json()["total"] == 3


def test_ranked_export_says_when_the_window_cut_it_short(client: TestClient) -> None:
    res = client.get("/export", params={"q": "energy"})  # matches far more than the window
    assert res.headers["x-ledger-export-truncated"] == "true"
