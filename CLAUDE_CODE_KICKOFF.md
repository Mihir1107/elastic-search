# Project Kickoff: Email Investigation Search (working name: "Ledger")

You are starting a NEW repository from scratch. Read this entire document before doing anything. Then enter plan mode, produce a written plan for Phase 0 and Phase 1 only, and wait for my approval before writing code.

---

## 1. What we are building

A production-grade **email investigation / eDiscovery search product** built on Elasticsearch, using the public Enron email corpus as the dataset.

The user is an investigator, analyst, or lawyer who has a large email dump and needs to answer questions like:
- "Who talked about the Raptor partnerships, and when?"
- "Everything Kenneth Lay sent to Jeff Skilling in Q3 2001"
- "Emails that discuss hiding losses, even if they never use those words"
- "Show me the whole thread this email belongs to"

They type into ONE search box (with optional filters). They never choose between "fuzzy", "prefix" or "regexp". The system decides.

### Success criteria (MVP)
1. Ingest the full Enron corpus (about 500k emails) reproducibly with one command.
2. Single search box supporting: free text, "quoted phrases", field operators (`from:`, `to:`, `cc:`, `subject:`, `before:`, `after:`), typo tolerance, and semantic matching.
3. Faceted filtering: sender, recipient, date histogram, has-attachment, folder.
4. Highlighted snippets showing WHY a result matched.
5. Email detail view + thread reconstruction.
6. Measured relevance: an evaluation harness reporting NDCG@10 and MRR for BM25 vs vector vs hybrid vs hybrid+rerank, with numbers committed to the repo.
7. A real 3-node cluster where killing a node during live search causes zero failed requests, demonstrated by a script.
8. p95 search latency under 300ms (excluding reranking) on the full corpus on a laptop.

### Explicit non-goals for MVP
- User accounts, auth, multi-tenancy (design so they can be added; do not build them)
- Uploading arbitrary user datasets
- Cloud deployment
- Any paid Elastic feature (see Section 4)

---

## 2. Background: the prototype we are replacing

There is an existing tutorial repo: https://github.com/naitikjani2022/elastic_search_demo

It is a beginner blog companion: 6 standalone scripts + a Streamlit "search types explorer" over 20 hand-picked Enron emails. It demonstrates 14 query types (match, term, phrase, proximity, bool, wildcard, fuzzy, prefix, range, regexp, geo, kNN, hybrid, rerank) and snapshots. Clone it for reference only. **Do not fork it or build on its structure.**

### What is worth borrowing
- Query shapes in `app/search_logic.py`
- Manual Reciprocal Rank Fusion (k=60) in `_reciprocal_rank_fusion`
- Snapshot register/create/restore logic in `part6_ha_failover/snapshots.py`
- Date mapping lesson: `date` must list every format it will be queried with

### Known flaws you must NOT repeat
| # | Flaw in prototype | Required fix |
|---|---|---|
| 1 | 20 docs total; no scale testing | Full corpus, plus a 10k dev subset for fast iteration |
| 2 | User picks the query type from a dropdown | Query understanding layer builds the query automatically |
| 3 | `size=20` hardcoded, no pagination, no aggregations | `search_after` pagination, total hits, facets via aggregations |
| 4 | Single node; "failover" never demonstrated | 3-node Docker cluster + chaos script that kills a node mid-load |
| 5 | Reranker uses `text_similarity_reranker` (403 on Basic license) | Local cross-encoder reranker in the API service |
| 6 | No relevance measurement | Eval harness with judged query set |
| 7 | `localhost:9200` hardcoded in 8 files; security disabled | Central config via env vars (pydantic-settings); security ON with TLS in compose |
| 8 | Scripts delete the index on every run | Versioned indices behind an alias (`emails` -> `emails-v1`), zero-downtime reindex |
| 9 | Embeddings via one `es.update` per doc, silently capped at 200 | Batched encoding + `helpers.bulk` / `parallel_bulk`, embeddings computed at ingest |
| 10 | Whole body embedded; MiniLM truncates at ~256 tokens | Chunk bodies; store chunk vectors as `nested` dense_vector or a chunks index |
| 11 | CC dropped; `to` stored as one string; no email normalisation; empty dates break bulk | Proper parser (see Section 5) with logged, counted failures |
| 12 | kNN runs without filters, so hybrid ignores facets | Apply the same filter to both BM25 and kNN legs |
| 13 | Leading-wildcard and raw regexp exposed to user input | Never expose raw wildcard/regexp; validate and cap inputs; set query timeouts |
| 14 | No highlighting | `highlight` on subject/body with fragment snippets |
| 15 | Unpinned dependencies, no tests, no Docker, no logging | Pinned deps, pytest, compose, structured logging |

---

## 3. Architecture

```
            +--------------------+
            |  web (Next.js)     |  single search box, facets, results, email view, thread view
            +---------+----------+
                      | HTTP/JSON
            +---------v----------+
            |  api (FastAPI)     |  query parser -> query builder -> ES -> fusion -> rerank
            +---------+----------+
                      |
      +---------------+----------------+
      |   Elasticsearch 3-node cluster |   es01 / es02 / es03, replicas=1
      +---------------+----------------+
                      ^
            +---------+----------+
            | ingest (Python CLI)|  download -> parse -> normalise -> thread -> chunk -> embed -> bulk
            +--------------------+
```

### Stack (pinned; check current stable versions before pinning)
- **Elasticsearch 9.x** official Docker image, **3 nodes**, `xpack.security.enabled: true` with generated certs (use Elastic's official docker-compose example as the base). Kibana optional behind a compose profile.
- **Python 3.12**, `uv` for dependency management
- **API:** FastAPI + official `elasticsearch` Python client (async), pydantic v2, pydantic-settings
- **Embeddings:** `sentence-transformers`, model `BAAI/bge-small-en-v1.5` (384 dims), cosine similarity. Keep the model name in config so it can be swapped.
- **Reranker:** `cross-encoder/ms-marco-MiniLM-L-6-v2`, runs over the top 50 fused results
- **Frontend:** Next.js (App Router) + TypeScript + Tailwind
- **Tests:** pytest + testcontainers (spin up real ES for integration tests)
- **Tooling:** ruff, mypy, pre-commit, Makefile

### Hardware constraint
Development machine is a **MacBook Air M3, 16GB RAM**. Three ES nodes + the embedding model + Next.js must fit. Set each ES node to 1GB heap (`ES_JAVA_OPTS=-Xms1g -Xmx1g`) with container memory limits, and provide a `single-node` compose profile for day-to-day work. Full-corpus embedding on CPU/MPS will take a long time: make ingestion resumable and checkpointed, and make embedding a separate stage that can run overnight.

---

## 4. Licensing rules (important)

We run on the free **Basic** license. The prototype hit 403s on:
- Native RRF (`rank: {"rrf": {}}` / `rrf` retriever)
- `text_similarity_reranker` retriever

At startup, the API must call the license endpoint and log the tier. **Verify against current Elastic docs which retrievers are available on Basic in the version you pin** (licensing has shifted across 8.x/9.x). If native RRF is available on Basic, use it; otherwise use manual RRF in Python. Reranking always runs locally. Nothing in the product may silently depend on a paid feature.

---

## 5. Data

### Source
Enron email corpus, CMU release (May 2015 version, `maildir` format, ~1.7GB compressed, ~500k messages across ~150 mailboxes). Find the current official download URL; do not commit the data to git.

### Ingestion pipeline stages (each resumable, each idempotent)
1. **download**: fetch + checksum + extract to `data/raw/` (gitignored)
2. **parse**: use Python's `email` stdlib parser, not string splitting. Extract: message_id, in_reply_to/references (if present), from, to[], cc[], bcc[], date (to UTC ISO-8601), subject, body (plain text; strip quoted replies into a separate `quoted_text` field), mailbox owner, folder path, attachment names (Enron data mostly has references only).
3. **normalise**: lowercase addresses, dedupe recipients, map known aliases for the same person to a `person_id` where possible (keep this simple for MVP: exact address plus X-From display name).
4. **dedupe**: the same email appears in many mailboxes. Hash (from, to, date, subject, body) and store one canonical doc with an array of `mailboxes` it appeared in.
5. **thread**: build `thread_id` from Message-ID/In-Reply-To where present; fall back to normalised subject (strip Re:/Fw:) + participants + time window.
6. **chunk + embed**: chunk body to about 200 tokens with overlap; embed in batches; store vectors.
7. **index**: bulk into a versioned index; flip the alias only after the document count and a smoke query pass.

Every stage writes a stats JSON: processed / skipped / failed with reasons. Failures are logged, never silently dropped.

Provide `make ingest-dev` (10k-email subset, deterministic sample) and `make ingest-full`.

### Mapping requirements
- `from`, `to`, `cc`: `keyword` with a lowercase normalizer, plus a `.text` subfield for name search
- `subject`, `body`: `text` with the english analyzer, plus a `.exact` subfield (standard analyzer) for phrase precision
- `date`: `date`, stored UTC
- `thread_id`, `mailbox`, `folder`, `person_id`: `keyword`
- chunk vectors: `dense_vector`, 384 dims, cosine, HNSW defaults, `index: true`
- Index settings: 3 primary shards, 1 replica. Document why this shard count suits this corpus size.

---

## 6. Search behaviour

### Query understanding layer (`api/search/parser.py`)
Parse the raw query string into a structured object:
- `"quoted text"` -> phrase clause on `subject.exact`/`body.exact`
- `from:x`, `to:x`, `cc:x` -> term filter on the normalised address, or match on `.text` if it is not an address
- `before:YYYY-MM-DD`, `after:YYYY-MM-DD` -> range filter
- Remaining free text -> the hybrid retrieval path
- Fuzziness: `AUTO` on free-text terms of length 5 or more only
- Unit-test the parser heavily; it is the core of the product.

### Retrieval pipeline
1. **BM25 leg:** `multi_match` over subject^3, body, from.text, to.text with filters
2. **Vector leg:** kNN over chunk vectors with the SAME filters (use kNN `filter`), collapse chunks to parent email
3. **Fusion:** RRF (native if Basic allows, else manual, k=60)
4. **Rerank:** cross-encoder over the top 50, behind a request flag and a config flag, with latency logged separately
5. **Highlight:** from the BM25 leg; for semantic-only hits, return the best-matching chunk as the snippet
6. **Facets:** aggregations for top senders, top recipients, date_histogram (month), folder

### API endpoints (v1)
- `GET /search?q=&page_token=&size=&rerank=&filters...` -> results, total, facets, timing breakdown per stage
- `GET /emails/{id}` -> full email
- `GET /threads/{thread_id}` -> ordered thread
- `GET /health` -> API + cluster health + license tier + active index version
- `GET /suggest?prefix=` -> autocomplete on people and subjects (use `search_as_you_type` or completion suggester)

Every ES call has a timeout. Every response includes `took_ms` per stage.

---

## 7. Relevance evaluation (`eval/`)

- Create 40 to 60 test queries spanning: exact lookup, person + topic, date-scoped, conceptual/no shared keywords, typo'd queries.
- Judgments: graded 0-3 per (query, doc). Bootstrap candidate pools from the union of the top 20 of every method. Build a small CLI to label them, and allow LLM-assisted pre-labelling, but I will review the judgments by hand.
- Metrics: NDCG@10, MRR, Recall@50 for BM25, vector, hybrid, hybrid+rerank.
- Output a markdown report `eval/results/<date>.md`. CI fails if hybrid NDCG@10 regresses by more than 2 points against the committed baseline.

---

## 8. High availability demo (`ops/chaos/`)

A script that:
1. Starts a load generator (e.g. `locust` headless or a simple async client) firing real queries
2. Kills one ES node with `docker kill`
3. Records cluster health transitions (green -> yellow -> green), replica promotion, and request success rate
4. Restarts the node and shows shard recovery
5. Prints a summary: total requests, failed requests (target 0), p50/p95 latency before, during, and after

Also: a snapshot repository in compose (shared volume), `make snapshot`, and `make restore` into a NEW index version without deleting the live one.

---

## 9. Repository layout

```
.
├── CLAUDE.md                 # conventions for future sessions (create in Phase 0)
├── README.md
├── Makefile
├── docker-compose.yml        # 3-node ES (+ kibana profile, single-node profile)
├── .env.example
├── api/
│   ├── pyproject.toml
│   ├── app/
│   │   ├── main.py
│   │   ├── config.py
│   │   ├── es.py
│   │   ├── search/ (parser.py, builder.py, fusion.py, rerank.py, facets.py)
│   │   └── routes/
│   └── tests/
├── ingest/
│   ├── pyproject.toml
│   ├── ingest/ (download.py, parse.py, normalise.py, dedupe.py, thread.py, embed.py, index.py, cli.py)
│   ├── mappings/emails.json
│   └── tests/
├── web/                      # Next.js
├── eval/
└── ops/ (chaos/, snapshots/)
```

---

## 10. Phases (stop and wait for my approval at every gate)

**Phase 0: Foundation.** Repo skeleton, CLAUDE.md, Makefile, compose (3-node + single-node profiles, security on), config, pinned deps, CI (ruff, mypy, pytest). Gate: `make up` gives a green 3-node cluster; `make test` passes.

**Phase 1: Ingestion.** All stages against the 10k dev subset. Mapping + alias. Gate: stats report shows 0 unexplained failures; spot-check 20 parsed emails against raw files.

**Phase 2: Search API.** Parser, BM25 + vector + fusion + facets + highlight + pagination. Gate: parser test coverage above 90%; example queries return sensible results.

**Phase 3: Evaluation.** Query set, labelling CLI, metrics report. Gate: baseline numbers committed.

**Phase 4: Rerank + tuning.** Cross-encoder, field boosts, and chunking tuned against eval numbers. Gate: every change justified by a metric delta.

**Phase 5: Frontend.** Search box, facets, results, email view, thread view, timing panel.

**Phase 6: Scale + HA.** Full corpus ingest, latency benchmark, chaos script, snapshots. Gate: p95 target met; chaos run shows 0 failed requests.

---

## 11. Working rules

- Plan before coding in each phase; list files you will create or change.
- Small commits with conventional commit messages.
- Do not invent Elasticsearch APIs. When unsure about a parameter, retriever, or license tier, check the official docs for the pinned version and cite the page in a code comment.
- Never delete a live index. Never commit data, model weights, or secrets.
- Prefer boring, explicit code over clever abstractions.
- If a requirement here is wrong or conflicts with reality (versions, licensing, memory), say so and propose an alternative instead of working around it silently.
- Keep a running `DECISIONS.md` log: decision, alternatives considered, reason.

Start now: read this, clone the prototype for reference, then give me the Phase 0 + Phase 1 plan.
