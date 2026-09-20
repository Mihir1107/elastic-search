# Ledger — product specification

The requirements this project was built against. `DECISIONS.md` records why each
one was implemented the way it was, including the three places where this
specification turned out to be wrong.

---

## 1. What this is

An email investigation / eDiscovery search product built on Elasticsearch, using
the public Enron corpus as its dataset.

The user is an investigator, analyst or lawyer holding a large email dump who
needs to answer questions like:

- Who talked about the Raptor partnerships, and when?
- Everything Kenneth Lay sent to Jeff Skilling in Q3 2001.
- Emails that discuss hiding losses, even if they never use those words.
- Show me the whole thread this email belongs to.

They type into **one** search box, with optional filters. They never choose
between "fuzzy", "prefix" or "regexp" — the system decides.

## 2. Success criteria

| # | Criterion | Status |
|---|---|---|
| 1 | Ingest the corpus reproducibly with one command | Partial — 100k of 517,401 messages (see D27) |
| 2 | One search box: free text, phrases, `from:`/`to:`/`cc:`/`subject:`/`before:`/`after:`, typo tolerance, semantic matching | Met |
| 3 | Faceted filtering: sender, recipient, date histogram, attachments, folder | Met |
| 4 | Highlighted snippets showing *why* a result matched | Met |
| 5 | Email detail view and thread reconstruction | Met |
| 6 | Measured relevance: NDCG@10 and MRR for BM25 / vector / hybrid / hybrid+rerank, committed to the repo | Met |
| 7 | A 3-node cluster where killing a node during live search causes zero failed requests | Met |
| 8 | p95 search latency under 300 ms (excluding reranking) | Met on the 100k corpus |

Criteria 1 and 8 say "the full corpus". The shipped index holds 100,000 parsed
messages (52,219 unique documents) rather than all 517,401. This is a deliberate,
recorded shortfall — see **D27** — taken because the full ingest costs 5–7 hours
and needs the dedupe stage rewritten to spill to disk. Latency was shown to track
concurrency rather than corpus size (**F16**), which is why the claim still holds.

### Explicit non-goals

User accounts, auth and multi-tenancy; uploading arbitrary datasets; cloud
deployment; any paid Elastic feature.

## 3. Licensing constraint

Everything runs on the free **Basic** licence. Nothing may silently depend on a
paid feature. The API probes the licence at startup and logs the tier.

Two features are unavailable on Basic and were replaced:

- **Native RRF** (`rrf` retriever) — 403s on Basic. Fusion is manual Reciprocal
  Rank Fusion at k=60, in Python (D1, confirmed empirically in F6).
- **`text_similarity_reranker`** — reranking is a local cross-encoder instead.

## 4. Data pipeline

Source: the CMU Enron release (May 2015, maildir format, ~1.4 GB extracted,
517,401 messages across 150 mailboxes). Never committed.

Each stage is resumable, idempotent, and writes a stats JSON recording
processed / skipped / failed with reasons. Failures are counted, never silently
dropped.

1. **download** — fetch, verify the checksum, extract
2. **parse** — the `email` stdlib parser (not string splitting): message id,
   reply headers, from, to, cc, date (UTC), subject, body, quoted text, mailbox,
   folder, attachment names
3. **normalise** — lowercase addresses, dedupe recipients, assign `person_id`
4. **dedupe** — the same email appears in many mailboxes; hash the content and
   keep one canonical document listing every mailbox it appeared in
5. **thread** — `thread_id` from reply headers, falling back to normalised
   subject plus participants in a time window
6. **chunk + embed** — chunk bodies to ~200 tokens with overlap, embed in batches
7. **index** — bulk into a versioned index; flip the alias only after the
   document count and a smoke query pass

### Mapping requirements

- `from`, `to`, `cc`: `keyword` with a lowercase normalizer, plus a `.text`
  subfield for name search
- `subject`, `body`: `text` with the english analyzer, plus an `.exact` subfield
- `date`: `date`, stored UTC
- `thread_id`, `mailbox`, `folder`, `person_id`: `keyword`
- chunk vectors: nested `dense_vector`, 384 dims, cosine, `index: true`
- 3 primary shards, 1 replica — chosen for failover topology, not data size (D4)

## 5. Search behaviour

**Query understanding** (`api/app/search/parser.py`) turns the raw string into a
structured query: quoted text becomes a phrase clause on the `.exact` subfields;
`from:`/`to:`/`cc:` become term filters on the normalised address (or a match on
`.text` when the value is not an address); `before:`/`after:` become a range
filter; the remainder goes to hybrid retrieval. Fuzziness is `AUTO` on free-text
terms of 5 characters or more.

**Retrieval pipeline:**

1. BM25 leg — `multi_match` over subject, body, `from.text`, `to.text`, with filters
2. Vector leg — kNN over nested chunk vectors carrying the **same** filters,
   collapsed to the parent email
3. Fusion — manual RRF, k=60
4. Rerank — a local cross-encoder over the top 50, behind a request flag and a
   config flag, with its latency reported separately. **Off by default** (D25)
5. Highlight — from the BM25 leg; semantic-only hits return their best chunk
6. Facets — top senders, top recipients, monthly date histogram, folder

Every Elasticsearch call has a timeout. Every response reports per-stage timing.

## 6. API

| Endpoint | Purpose |
|---|---|
| `GET /search` | results, total, facets, per-stage timing |
| `GET /emails/{id}` | one email in full |
| `GET /threads/{thread_id}` | the ordered thread |
| `GET /suggest?prefix=` | autocomplete over people and subjects |
| `GET /health` | API + cluster health, licence tier, active index |

## 7. Relevance evaluation

40–60 queries spanning exact lookup, person + topic, date-scoped, conceptual and
typo'd. Judgments are graded 0–3, pooled from the union of the top 20 of every
method. Metrics: NDCG@10, MRR, Recall@50. CI fails if hybrid NDCG@10 regresses
more than 2 points against the committed baseline.

Where relevance is derivable from the document itself — a required phrase, a
named sender, a date window — the query declares an objective rule and is graded
reproducibly (D19). Conceptual queries carry no such rule and need a human.

## 8. High availability

A script that starts a load generator, kills one node with `docker kill`, records
the health transitions and replica promotion, restarts the node, and reports
total requests, failed requests (target zero) and p50/p95 before, during and
after. Plus a snapshot repository, and restore into a **new** index version
without touching the live one.

---

## Appendix — flaws in the prototype this replaces

This project began as a replacement for a tutorial-grade prototype (6 scripts
and a Streamlit "search types explorer" over 20 hand-picked emails). Code
comments refer to these by number.

| # | Flaw in the prototype | Required fix |
|---|---|---|
| 1 | 20 documents; no scale testing | Full corpus, plus a deterministic dev subset |
| 2 | The user picks the query type from a dropdown | A query-understanding layer builds the query |
| 3 | `size=20` hardcoded, no pagination, no aggregations | Pagination, total hits, facets via aggregations |
| 4 | Single node; failover never demonstrated | 3-node cluster plus a chaos script |
| 5 | Reranker used `text_similarity_reranker` (403 on Basic) | A local cross-encoder in the API |
| 6 | No relevance measurement | An evaluation harness with a judged query set |
| 7 | `localhost:9200` hardcoded in 8 files; security disabled | Central config via env vars; TLS and auth on |
| 8 | Scripts deleted the index on every run | Versioned indices behind an alias |
| 9 | One `es.update` per document, silently capped at 200 | Batched encoding and bulk indexing |
| 10 | The whole body embedded; the model truncates at ~256 tokens | Chunked bodies with per-chunk vectors |
| 11 | CC dropped; `to` stored as one string; empty dates broke bulk | A real parser with counted failures |
| 12 | kNN ran without filters, so hybrid ignored facets | The same filters applied to both legs |
| 13 | Leading-wildcard and raw regexp exposed to user input | Never expose raw wildcard/regexp; validate and cap |
| 14 | No highlighting | `highlight` on subject and body |
| 15 | Unpinned dependencies, no tests, no Docker, no logging | Pinned deps, pytest, compose, structured logging |
