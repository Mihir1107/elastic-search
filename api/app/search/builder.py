"""Build Elasticsearch requests from a ParsedQuery.

Two retrieval legs share the SAME filters (spec flaw #12: the prototype ran
kNN unfiltered, so hybrid results ignored the facets the user had selected).
Nothing here ever emits a wildcard/regexp/query_string clause, so user input
carries no query-language meaning (flaw #13).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from app.search.parser import FUZZINESS, ParsedQuery, is_address

#: subject is boosted; from/to .text let a name match without an address.
BM25_FIELDS = ["subject^3", "body", "from.text", "to.text"]

#: Cap how much of a body the highlighter re-analyses. Highlighting is by far the
#: most expensive part of a search (measured: ~1.9s for 200 docs vs 45ms without),
#: and fragments in practice come from the first part of an email anyway.
MAX_ANALYZED_OFFSET = 100_000

#: <em> is what the web client's Marker component splits on. It rebuilds the
#: fragment from text nodes rather than trusting the HTML, so document content
#: cannot inject markup -- which only works if the tag is the one it expects.
HIGHLIGHT: dict[str, Any] = {
    "pre_tags": ["<em>"],
    "post_tags": ["</em>"],
    "encoder": "html",
    "max_analyzed_offset": MAX_ANALYZED_OFFSET,
    "fields": {
        "subject": {"number_of_fragments": 0},
        "subject.exact": {"number_of_fragments": 0},
        "body": {"fragment_size": 160, "number_of_fragments": 2, "no_match_size": 0},
        "body.exact": {"fragment_size": 160, "number_of_fragments": 2},
    },
}


#: Order of preference when several highlighted fields matched.
_HIGHLIGHT_PREFERENCE = ("body.exact", "body", "subject.exact", "subject")


def _address_clause(field: str, value: str) -> dict[str, Any]:
    """Exact term on the normalised address, or a name match on the .text subfield."""
    if is_address(value):
        return {"term": {field: value}}
    return {"match": {f"{field}.text": {"query": value, "operator": "and"}}}


def build_filters(query: ParsedQuery) -> list[dict[str, Any]]:
    filters: list[dict[str, Any]] = []
    for field, values in (
        ("from", query.from_),
        ("to", query.to),
        ("cc", query.cc),
    ):
        clauses = [_address_clause(field, value) for value in values]
        if len(clauses) == 1:
            filters.append(clauses[0])
        elif clauses:
            filters.append({"bool": {"should": clauses, "minimum_should_match": 1}})

    for value in query.subject:
        filters.append({"match": {"subject": {"query": value, "operator": "and"}}})

    if query.after or query.before:
        rng: dict[str, str] = {}
        if query.after:
            rng["gte"] = query.after.isoformat()
        if query.before:
            # inclusive of the whole day
            rng["lte"] = f"{query.before.isoformat()}T23:59:59.999Z"
        filters.append({"range": {"date": rng}})
    return filters


@dataclass(frozen=True)
class StructuredFilters:
    """Filters supplied as query parameters rather than inside the query string.

    This is what the UI sends when someone clicks a facet. Several values for
    one field are OR-ed; different fields are AND-ed, which is what a facet
    sidebar means by "sender = A or B, and folder = inbox".
    """

    from_: tuple[str, ...] = ()
    to: tuple[str, ...] = ()
    cc: tuple[str, ...] = ()
    folder: tuple[str, ...] = ()
    after: date | None = None
    before: date | None = None
    has_attachment: bool | None = None

    def is_empty(self) -> bool:
        return not (
            self.from_
            or self.to
            or self.cc
            or self.folder
            or self.after
            or self.before
            or self.has_attachment is not None
        )


def _any_of(field: str, values: tuple[str, ...]) -> dict[str, Any] | None:
    clauses = [_address_clause(field, v) for v in values]
    if not clauses:
        return None
    if len(clauses) == 1:
        return clauses[0]
    return {"bool": {"should": clauses, "minimum_should_match": 1}}


def build_structured_filters(f: StructuredFilters) -> list[dict[str, Any]]:
    filters: list[dict[str, Any]] = []
    for field, values in (("from", f.from_), ("to", f.to), ("cc", f.cc)):
        clause = _any_of(field, values)
        if clause:
            filters.append(clause)
    if f.folder:
        filters.append({"terms": {"folder": list(f.folder)}})
    if f.after or f.before:
        rng: dict[str, str] = {}
        if f.after:
            rng["gte"] = f.after.isoformat()
        if f.before:
            rng["lte"] = f"{f.before.isoformat()}T23:59:59.999Z"
        filters.append({"range": {"date": rng}})
    if f.has_attachment is not None:
        filters.append({"term": {"has_attachment": f.has_attachment}})
    return filters


def build_bm25_query(
    query: ParsedQuery,
    filters: list[dict[str, Any]],
    fields: list[str] | None = None,
) -> dict[str, Any]:
    must: list[dict[str, Any]] = []

    if query.terms:
        must.append(
            {
                "multi_match": {
                    "query": query.text,
                    "fields": fields or BM25_FIELDS,
                    "type": "best_fields",
                    # AUTO:5,8 -> exact below 5 chars, then 1 then 2 edits.
                    "fuzziness": FUZZINESS,
                    "prefix_length": 1,
                    "max_expansions": 50,
                }
            }
        )

    for phrase in query.phrases:
        must.append(
            {
                "bool": {
                    "should": [
                        {"match_phrase": {"subject.exact": {"query": phrase, "boost": 3}}},
                        {"match_phrase": {"body.exact": phrase}},
                    ],
                    "minimum_should_match": 1,
                }
            }
        )

    if not must:
        must.append({"match_all": {}})

    return {"bool": {"must": must, "filter": filters}}


def build_knn(
    vector: list[float],
    filters: list[dict[str, Any]],
    k: int,
    num_candidates: int,
) -> dict[str, Any]:
    """kNN over nested chunk vectors, carrying the same filters as the BM25 leg.

    ``inner_hits`` returns the single best-matching chunk, which becomes the
    snippet for hits that only the semantic leg found.
    """
    knn: dict[str, Any] = {
        "field": "chunks.vector",
        "query_vector": vector,
        "k": k,
        "num_candidates": num_candidates,
        "inner_hits": {
            "size": 1,
            "name": "chunk",
            "_source": ["chunks.text"],
        },
    }
    if filters:
        knn["filter"] = {"bool": {"filter": filters}}
    return knn


def best_highlight(highlight: dict[str, list[str]] | None) -> list[str]:
    """Pick the most useful highlighted fragments from an ES highlight block."""
    if not highlight:
        return []
    for field in _HIGHLIGHT_PREFERENCE:
        fragments = highlight.get(field)
        if fragments:
            return list(fragments)
    return []
