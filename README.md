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

## Repository layout

```
api/       FastAPI service (app/, tests/)          ingest/   ingestion CLI (ingest/, mappings/, tests/)
web/       Next.js frontend (Phase 5)              eval/     relevance harness (Phase 3)
ops/       chaos + snapshot demos (Phase 6)        scripts/  preflight / certs / health helpers
docker-compose.yml   3-node ES (+ single, kibana profiles)   Makefile   developer entry points
```

See `make help` for all targets and `CLAUDE.md` for conventions.
