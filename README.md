# Ledger — email investigation search

A production-grade email investigation / eDiscovery search product built on
Elasticsearch, using the public **Enron** corpus as the dataset. One search box:
free text, `"quoted phrases"`, field operators (`from:`, `to:`, `cc:`, `subject:`,
`before:`, `after:`), typo tolerance, and semantic matching — the system decides how
to query; the user never picks "fuzzy" vs "prefix".

> Status: **Phase 0 (Foundation)** complete. Phases 1–6 follow the gates in
> `CLAUDE_CODE_KICKOFF.md`. See `DECISIONS.md` for the decision log.

## Architecture

```
 web (Next.js)  ->  api (FastAPI)  ->  Elasticsearch 3-node cluster (TLS)
                          ^
                     ingest (Python CLI): download -> parse -> normalise ->
                     dedupe -> thread -> chunk+embed -> bulk index (alias flip)
```

- **Elasticsearch 9.5.3**, 3 nodes, security + TLS on, Basic license.
- **API**: FastAPI + async `elasticsearch` client. Retrieval = BM25 + kNN legs
  fused with **manual RRF (k=60)** (no paid features), optional local cross-encoder rerank.
- **Embeddings**: `BAAI/bge-small-en-v1.5` (384-d, cosine); chunked bodies as nested vectors.
- **Python 3.12**, managed with **uv** (one workspace, one shared venv).

## Quickstart

```bash
make install        # create .venv, install api + ingest + dev tools (downloads torch)
make preflight      # docker running? disk? python? (creates .env if missing)
make up             # start the 3-node cluster, wait for green, export the CA cert
make health         # cluster health + license tier
make test           # fast unit tests (no ES)
make down           # stop + remove volumes
```

Day-to-day on a laptop, prefer a single node: `make up-single`. Kibana (optional):
`make up-kibana` (then http://localhost:5601, user `elastic`).

**Before real use:** copy `.env.example` to `.env` and change `ELASTIC_PASSWORD`
and `KIBANA_PASSWORD`. Never commit `.env`, `data/`, `certs/`, or model weights.

## Ingestion

```bash
make ingest-dev     # download -> parse -> normalise -> dedupe -> thread -> embed -> index
                    # over a deterministic 10k-message subset of the real Enron corpus
make ingest-full    # the same pipeline over all ~500k messages
make stats          # per-stage processed / skipped / failed counts, with reasons
make spotcheck      # compare 20 parsed documents against their raw maildir files
```

Stages can also be run individually (`uv run python -m ingest.cli parse --subset dev`).
Every stage is resumable and idempotent: documents are content-addressed, so re-running
upserts rather than duplicates. Data lands in a versioned index (`emails-v1`) and the
`emails` alias is moved only after the document count and a smoke query pass.

## Search API

```bash
uv run uvicorn app.main:app --app-dir api --reload    # http://localhost:8000/docs
```

| Endpoint | Purpose |
|---|---|
| `GET /search?q=&size=&page_token=` | the single search box; returns hits, facets, timings |
| `GET /emails/{id}` | one full email |
| `GET /threads/{thread_id}` | the whole conversation, in order |
| `GET /suggest?prefix=` | autocomplete over people and subjects |
| `GET /health` | API + cluster health, license tier, active index behind the alias |

The search box takes free text, `"quoted phrases"`, `from:`/`to:`/`cc:`/`subject:`
and `before:`/`after:` — the system builds the query; the user never picks a query type:

```
raptor partnership from:kenneth.lay@enron.com after:2001-07-01 "hiding losses"
```

Retrieval runs a BM25 leg and a kNN leg over nested chunk vectors **with the same
filters**, fuses them with manual RRF (k=60), and returns highlighted snippets —
falling back to the best-matching chunk for hits only the semantic leg found.
Every response carries a per-stage `timings` breakdown and echoes back how the
query was `understood`.

## Repository layout

```
api/       FastAPI service (app/, tests/)          ingest/   ingestion CLI (ingest/, mappings/, tests/)
web/       Next.js frontend (Phase 5)              eval/     relevance harness (Phase 3)
ops/       chaos + snapshot demos (Phase 6)        scripts/  preflight / certs / health helpers
docker-compose.yml   3-node ES (+ single, kibana profiles)   Makefile   developer entry points
```

See `make help` for all targets and `CLAUDE.md` for conventions.
