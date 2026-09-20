# Contributing

Conventions for working in this repository. `docs/SPEC.md` is the product
specification; `DECISIONS.md` records why things are the way they are.

## Stack and pins

- **Elasticsearch 9.5.3** (server and Docker image); Python client `elasticsearch==9.5.1`
- **Python 3.12**, managed by **uv** as a workspace: the root `pyproject.toml`
  lists `api` and `ingest` as members sharing **one** `.venv`, so torch installs
  once. `make install` runs `uv sync --all-packages --all-groups`
- Dependencies are pinned with `==` (fastapi 0.141.1, pydantic 2.13.5,
  pydantic-settings 2.15.0, sentence-transformers 6.1.0, typer 0.27.2,
  ruff 0.16.8, mypy 2.3.1, pytest 9.1.1)
- Frontend: Next.js 15 App Router, React 19, Tailwind v4, pinned exactly

## Hard rules

- **Basic licence only.** Nothing may depend on a paid feature. RRF is done
  manually in Python (D1); reranking is a local cross-encoder, never Elastic's
  `text_similarity_reranker`. The API logs the licence tier at startup.
- **Never delete a live index.** Write to `emails-vN`, verify the document count
  and a smoke query, then flip the `emails` alias. Reindex to a new version;
  never drop the serving index.
- **Never commit** `data/`, `eval/pools.json`, model weights, `certs/`, `.env`,
  `web/.env.local`, `node_modules/` or `.next/` — all are gitignored.
- **No hardcoded hosts or credentials.** All configuration goes through
  `pydantic-settings` and `.env` (`api/app/config.py`, `ingest/ingest/config.py`).
  The password comes from `ELASTIC_PASSWORD`.
- **Don't invent Elasticsearch APIs.** When unsure about a parameter, retriever
  or licence tier, check the 9.5.x docs and cite the page in a code comment.
- Prefer boring, explicit code over clever abstractions.

## Measurement rules

This project's relevance and latency numbers are load-bearing, so:

- **Every tuning change must be justified by a measured delta.** If a change
  does not earn its keep, revert it and say so. Several have been.
- `uv run python -m eval.cli check` must stay green. It fails on a hybrid
  NDCG@10 drop of more than 2 points against the committed baseline.
- **Changing the corpus invalidates the judged pool.** Unjudged documents score
  zero, so a bigger index looks like a relevance collapse. Re-run
  `make eval-pool` then `make eval-baseline` as part of any corpus change (F14).
- Benchmark against a production-mode server with exactly one listener on the
  port. A `uvicorn --reload` supervisor is not representative (D30).

## Workflow

- Small commits with conventional messages (`feat:`, `fix:`, `chore:`, `docs:`).
- Quality gate before committing:

  ```bash
  make lint && make typecheck && make test
  ```

- Keep `DECISIONS.md` current: the decision, the alternatives, the reason. Record
  negative results too — knowing that something was tried and measured worse is
  worth as much as knowing what worked.

## Where things live

| Path | Contents |
|---|---|
| `docker-compose.yml` | 3-node cluster (profiles: default, `single`, `kibana`) |
| `scripts/` | preflight, cert export, health helpers |
| `ingest/mappings/emails.json` | the index mapping |
| `ingest/ingest/` | pipeline stages |
| `api/app/` | `config.py`, `es.py`, `main.py`, `search/`, `routes/` |
| `web/` | Next.js frontend |
| `eval/` | relevance harness, query set, judgments |
| `ops/` | latency benchmark, chaos run, snapshots |
| `*/tests/` | tests; integration tests are marked `@pytest.mark.integration` and need a running cluster |
