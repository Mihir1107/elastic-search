"""End-to-end API tests against the live cluster and whatever index the alias serves.

Marked ``integration``: needs Elasticsearch with the ``emails`` alias populated.
"""

from __future__ import annotations

import re
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
    # Exactly one concrete index behind the alias, and it is versioned. Asserting
    # a specific version would fail every time the corpus is reindexed, which is
    # the normal path (write emails-vN, verify, flip the alias).
    assert len(body["active_index"]) == 1
    assert re.fullmatch(r"emails-v\d+", body["active_index"][0]), body["active_index"]
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


def test_deep_pagination_at_ui_page_size_never_repeats(client: TestClient) -> None:
    """Regression: the fusion window must not grow with the page.

    The UI pages at size 20. With a per-page window the second page was fused
    from a larger candidate set than the first, which re-ranked everything and
    returned documents page one had already shown (React reported duplicate
    keys for real document ids).
    """
    seen: list[str] = []
    token: str | None = None
    for page in range(5):
        params: dict[str, Any] = {"q": "california power crisis", "size": 20}
        if token:
            params["page_token"] = token
        body = client.get("/search", params=params).json()
        ids = [h["id"] for h in body["hits"]]
        assert ids, f"page {page} returned nothing"
        repeats = sorted(set(ids) & set(seen))
        assert not repeats, f"page {page} repeated {len(repeats)} result(s): {repeats[:3]}"
        seen.extend(ids)
        token = body["next_page_token"]
        if not token:
            break
    assert len(seen) == len(set(seen))


def test_skipped_rerank_says_why(client: TestClient) -> None:
    """Regression: an operator query with rerank=true came back unchanged and silent.

    The gate (D23) is correct, but a skip with no explanation looked like a
    broken Rerank button in the UI.
    """
    q = "from:john.arnold@enron.com gas after:2001-07-01 before:2001-09-30"
    body = client.get("/search", params={"q": q, "size": 5, "rerank": "true"}).json()
    assert body["reranked"] is False
    assert body["timings"]["rerank_ms"] == 0
    assert any("reranking skipped" in w for w in body["warnings"]), body["warnings"]


def test_free_text_rerank_applies_and_is_not_flagged(client: TestClient) -> None:
    body = client.get("/search", params={"q": "gas prices", "size": 5, "rerank": "true"}).json()
    assert body["reranked"] is True
    assert body["timings"]["rerank_ms"] > 0
    assert not any("reranking skipped" in w for w in body["warnings"])


def test_a_quoted_phrase_constrains_the_vector_leg_too(client: TestClient) -> None:
    """A phrase is a requirement: kNN neighbours lacking it must not be fused in."""
    body = client.get("/search", params={"q": '"force majeure"', "size": 20}).json()
    assert body["hits"]
    assert any(hit["vector_rank"] is not None for hit in body["hits"])
    for hit in body["hits"]:
        email = client.get(f"/emails/{hit['id']}").json()
        text = " ".join(f"{email['subject']} {email['body']}".lower().split())
        assert "force majeure" in text, hit["id"]


def test_a_typo_is_corrected_for_the_embedder_and_reported(client: TestClient) -> None:
    body = client.get("/search", params={"q": "califronia energy crisis", "size": 5}).json()
    assert body["understood"]["corrections"] == [
        {"original": "califronia", "suggested": "california"}
    ]
    assert body["understood"]["terms"] == ["califronia", "energy", "crisis"]


def test_real_words_are_never_corrected(client: TestClient) -> None:
    for q in ("complaints that the new software keeps crashing", "hiding financial losses"):
        body = client.get("/search", params={"q": q, "size": 5}).json()
        assert body["understood"]["corrections"] == [], q


def test_every_hit_is_hydrated_with_its_document_fields(client: TestClient) -> None:
    body = client.get("/search", params={"q": "gas pipeline capacity", "size": 20}).json()
    assert body["hits"]
    for hit in body["hits"]:
        assert hit["message_id"] and hit["date"] and hit["from"]
        assert hit["snippets"], hit["id"]


def test_suggest_finds_senders_whatever_the_subjects_say(client: TestClient) -> None:
    """People come from the sender field, not from emails whose subject matched."""
    body = client.get("/suggest", params={"prefix": "kenneth.lay"}).json()
    people = [s["value"] for s in body["suggestions"] if s["kind"] == "person"]
    assert people and all(p.startswith("kenneth.lay") for p in people)


def test_later_pages_reuse_the_first_pages_ranking(client: TestClient) -> None:
    """Page two comes from the cached fused list: no retrieval is re-run."""
    first = client.get("/search", params={"q": "california power", "size": 10}).json()
    second = client.get(
        "/search",
        params={"q": "california power", "size": 10, "page_token": first["next_page_token"]},
    ).json()
    assert second["timings"]["bm25_ms"] == 0 and second["timings"]["knn_ms"] == 0
    assert not {h["id"] for h in first["hits"]} & {h["id"] for h in second["hits"]}


def test_thread_messages_carry_display_names_and_tags(client: TestClient) -> None:
    hit = next(
        h
        for h in client.get("/search", params={"q": "meeting", "size": 20}).json()["hits"]
        if h["thread_id"]
    )
    messages = client.get(f"/threads/{hit['thread_id']}").json()["messages"]
    assert all("tags" in m for m in messages)
    assert not any("/O=" in (m["from_name"] or "") for m in messages)
