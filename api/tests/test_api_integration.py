"""End-to-end API tests against the live cluster and the real dev-subset index.

Marked ``integration``: needs Elasticsearch with the ``emails`` alias populated.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def client() -> Iterator[TestClient]:
    from app.main import app

    with TestClient(app) as test_client:
        health = test_client.get("/health").json()
        if health.get("status") != "ok":
            pytest.skip(f"cluster not ready: {health}")
        yield test_client


def test_health_reports_cluster_license_and_active_index(client: TestClient) -> None:
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["elasticsearch"] in {"green", "yellow"}
    assert body["number_of_nodes"] >= 1
    # The product targets Basic and must not silently rely on a paid tier.
    assert body["license_tier"] == "basic"
    assert body["active_index"] == ["emails-v1"]
    assert isinstance(body["native_rrf_available"], bool)


def test_free_text_search_returns_hits_facets_and_timings(client: TestClient) -> None:
    body = client.get("/search", params={"q": "raptor partnership", "size": 5}).json()

    assert body["total"] > 0
    assert 0 < len(body["hits"]) <= 5
    assert body["understood"]["terms"] == ["raptor", "partnership"]

    hit = body["hits"][0]
    assert hit["id"] and "from" in hit
    assert hit["snippets"], "every hit must explain why it matched"
    assert set(hit["matched_by"]) <= {"bm25", "knn"}

    assert body["facets"]["top_senders"]
    assert body["facets"]["over_time"]
    # per-stage timing breakdown
    t = body["timings"]
    assert t["total_ms"] > 0 and t["bm25_ms"] > 0 and t["knn_ms"] > 0


def test_hybrid_uses_both_legs(client: TestClient) -> None:
    body = client.get("/search", params={"q": "unplanned losses", "size": 20}).json()
    legs = {leg for hit in body["hits"] for leg in hit["matched_by"]}
    assert "knn" in legs, "the vector leg must contribute"


def test_from_operator_filters_to_one_sender(client: TestClient) -> None:
    body = client.get("/search", params={"q": "from:john.arnold@enron.com", "size": 5}).json()
    assert body["total"] > 0
    assert body["understood"]["from"] == ["john.arnold@enron.com"]
    for hit in body["hits"]:
        assert hit["from"] == "john.arnold@enron.com"


def test_date_operators_restrict_the_range(client: TestClient) -> None:
    body = client.get(
        "/search", params={"q": "after:2001-10-01 before:2001-12-31", "size": 10}
    ).json()
    assert body["total"] > 0
    for hit in body["hits"]:
        assert "2001-10" <= hit["date"][:7] <= "2001-12"


def test_quoted_phrase_matches_exactly(client: TestClient) -> None:
    body = client.get("/search", params={"q": '"please let me know"', "size": 5}).json()
    assert body["total"] > 0
    assert body["understood"]["phrases"] == ["please let me know"]


def test_filters_apply_to_both_legs(client: TestClient) -> None:
    """Flaw #12: kNN must honour the same filters as BM25."""
    body = client.get(
        "/search", params={"q": "schedule from:pete.davis@enron.com", "size": 20}
    ).json()
    assert body["total"] > 0
    for hit in body["hits"]:
        assert hit["from"] == "pete.davis@enron.com"


def test_pagination_walks_without_repeating(client: TestClient) -> None:
    """Walk several pages twice over.

    Each page is a fresh search, so without a pinned shard preference and a
    deterministic tiebreaker the fused window shifts between requests and pages
    overlap. Repeating the walk makes that instability reproducible rather than
    an occasional flake.
    """
    for attempt in range(3):
        seen: list[str] = []
        token: str | None = None
        for page in range(3):
            params: dict[str, Any] = {"q": "enron", "size": 5}
            if token:
                params["page_token"] = token
            body = client.get("/search", params=params).json()
            ids = [h["id"] for h in body["hits"]]
            assert ids, f"attempt {attempt} page {page} returned nothing"
            overlap = set(ids) & set(seen)
            assert not overlap, f"attempt {attempt} page {page} repeated {len(overlap)} result(s)"
            seen.extend(ids)
            token = body["next_page_token"]
            if not token:
                break
        assert len(seen) == len(set(seen))


def test_pagination_is_stable_across_identical_requests(client: TestClient) -> None:
    """The same query must return the same page every time."""
    params = {"q": "schedule crawler", "size": 10}
    runs = [
        [h["id"] for h in client.get("/search", params=params).json()["hits"]] for _ in range(3)
    ]
    assert runs[0] == runs[1] == runs[2], "identical queries returned different orders"


def test_bad_page_token_is_tolerated(client: TestClient) -> None:
    body = client.get("/search", params={"q": "enron", "page_token": "!!not-b64!!"}).json()
    assert body["hits"]


def test_empty_query_returns_recent_mail(client: TestClient) -> None:
    body = client.get("/search", params={"q": "", "size": 5}).json()
    assert body["total"] > 0
    dates = [h["date"] for h in body["hits"] if h["date"]]
    assert dates == sorted(dates, reverse=True), "empty query should sort by recency"


def test_warnings_surface_to_the_caller(client: TestClient) -> None:
    body = client.get("/search", params={"q": "after:nonsense raptor"}).json()
    assert any("YYYY-MM-DD" in w for w in body["warnings"])


def _any_hit(client: TestClient) -> dict[str, Any]:
    body = client.get("/search", params={"q": "enron", "size": 1}).json()
    return dict(body["hits"][0])


def test_email_detail_round_trip(client: TestClient) -> None:
    hit = _any_hit(client)
    detail = client.get(f"/emails/{hit['id']}").json()
    assert detail["id"] == hit["id"]
    assert detail["from"] == hit["from"]
    assert "body" in detail


def test_unknown_email_is_404(client: TestClient) -> None:
    assert client.get("/emails/does-not-exist").status_code == 404


def test_thread_view_is_ordered(client: TestClient) -> None:
    hit = _any_hit(client)
    thread = client.get(f"/threads/{hit['thread_id']}").json()
    assert thread["total"] >= 1
    dates = [m["date"] for m in thread["messages"] if m["date"]]
    assert dates == sorted(dates), "thread must be in chronological order"


def test_unknown_thread_is_404(client: TestClient) -> None:
    assert client.get("/threads/nope").status_code == 404


def test_suggest_returns_people_and_subjects(client: TestClient) -> None:
    body = client.get("/suggest", params={"prefix": "john"}).json()
    kinds = {s["kind"] for s in body["suggestions"]}
    assert body["suggestions"]
    assert "person" in kinds


def test_suggest_empty_prefix_is_empty(client: TestClient) -> None:
    assert client.get("/suggest", params={"prefix": ""}).json()["suggestions"] == []


def test_suggest_sanitises_regex_input(client: TestClient) -> None:
    """A terms-agg include is a regex; metacharacters must not reach it."""
    response = client.get("/suggest", params={"prefix": ".*|(a)"})
    assert response.status_code == 200


def test_rerank_flag_is_reported_separately(client: TestClient) -> None:
    """Rerank latency must be its own number, never hidden inside total_ms."""
    off = client.get("/search", params={"q": "transmission congestion", "rerank": "false"}).json()
    on = client.get("/search", params={"q": "transmission congestion", "rerank": "true"}).json()
    assert off["timings"]["rerank_ms"] == 0.0
    assert on["timings"]["rerank_ms"] > 0.0


def test_rerank_is_skipped_when_the_user_gave_an_explicit_signal(
    client: TestClient,
) -> None:
    """A quoted phrase or a field operator is an explicit precision signal."""
    for q in ['"natural gas"', "from:john.arnold@enron.com gas"]:
        body = client.get("/search", params={"q": q, "rerank": "true"}).json()
        assert body["timings"]["rerank_ms"] == 0.0, f"{q} should not be reranked"


# --------------------------- structured facet filters ---------------------------


def test_facet_filter_narrows_results(client: TestClient) -> None:
    """Clicking a facet sends a structured parameter, not a rewritten query string."""
    base = client.get("/search", params={"q": "gas", "size": 5}).json()
    filtered = client.get(
        "/search", params={"q": "gas", "size": 5, "from": "john.arnold@enron.com"}
    ).json()
    assert 0 < filtered["total"] < base["total"]
    for hit in filtered["hits"]:
        assert hit["from"] == "john.arnold@enron.com"


def test_repeating_a_filter_ors_its_values(client: TestClient) -> None:
    one = client.get("/search", params={"q": "gas", "from": "john.arnold@enron.com"}).json()
    two = client.get(
        "/search",
        params={"q": "gas", "from": ["john.arnold@enron.com", "bill.williams@enron.com"]},
    ).json()
    assert two["total"] >= one["total"]


def test_different_filters_are_anded(client: TestClient) -> None:
    both = client.get(
        "/search",
        params={
            "q": "gas",
            "from": "john.arnold@enron.com",
            "after": "2001-07-01",
            "before": "2001-09-30",
        },
    ).json()
    for hit in both["hits"]:
        assert hit["from"] == "john.arnold@enron.com"
        assert "2001-07" <= hit["date"][:7] <= "2001-09"


def test_folder_facet_filter(client: TestClient) -> None:
    body = client.get("/search", params={"q": "", "folder": "sent_items", "size": 5}).json()
    assert body["total"] > 0
    for hit in body["hits"]:
        assert "sent_items" in hit["folder"]


def test_structured_filters_also_constrain_the_vector_leg(client: TestClient) -> None:
    """Flaw #12 again, now for facet-supplied filters rather than query operators."""
    body = client.get(
        "/search", params={"q": "power supply problems", "from": "pete.davis@enron.com", "size": 20}
    ).json()
    assert body["total"] > 0
    assert any("knn" in hit["matched_by"] for hit in body["hits"])
    for hit in body["hits"]:
        assert hit["from"] == "pete.davis@enron.com"


# --------------------------- fields the web client needs ---------------------------


def test_hits_carry_real_per_leg_ranks(client: TestClient) -> None:
    body = client.get("/search", params={"q": "california power", "size": 10}).json()
    for hit in body["hits"]:
        if "bm25" in hit["matched_by"]:
            assert isinstance(hit["bm25_rank"], int) and hit["bm25_rank"] >= 1
        else:
            assert hit["bm25_rank"] is None
        if "knn" in hit["matched_by"]:
            assert isinstance(hit["vector_rank"], int) and hit["vector_rank"] >= 1
        else:
            assert hit["vector_rank"] is None


def test_highlights_use_em_tags(client: TestClient) -> None:
    """The web client splits fragments on <em> and rebuilds them as text nodes."""
    body = client.get("/search", params={"q": "transmission outage", "size": 10}).json()
    fragments = [s for hit in body["hits"] for s in hit["snippets"]]
    assert any("<em>" in f for f in fragments)
    assert not any("<mark>" in f for f in fragments)


def test_sender_display_names_are_never_distinguished_names(client: TestClient) -> None:
    body = client.get("/search", params={"q": "california", "size": 25}).json()
    for hit in body["hits"]:
        assert "/O=" not in hit["from_name"].upper()
        assert "@" not in hit["from_name"]


def test_health_reports_shards_and_document_count(client: TestClient) -> None:
    body = client.get("/health").json()
    assert body["docs"] and body["docs"] > 0
    assert body["active_shards"] and body["active_shards"] > 0
