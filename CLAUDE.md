# CLAUDE.md — conventions for working in this repo

Read `CLAUDE_CODE_KICKOFF.md` for the full product spec and phase gates, and
`DECISIONS.md` for why things are the way they are. **Stop at each phase gate and
wait for approval** before starting the next phase.

## Stack & pins (verified 2026-09-20)
- Elasticsearch **9.5.3** (server + Docker image); Python client `elasticsearch==9.5.1`.
- Python **3.12**, managed by **uv** as a workspace: root `pyproject.toml` lists members
  `api` and `ingest`; they share ONE `.venv` (torch installed once). `make install` = `uv sync --all-packages --all-groups`.
- Key deps pinned with `==` (fastapi 0.141.1, pydantic 2.13.5, pydantic-settings 2.15.0,
  sentence-transformers 6.1.0, typer 0.27.2, ruff 0.16.8, mypy 2.3.1, pytest 9.1.1).

## Hard rules (from the kickoff)
- **Basic license only.** Nothing may depend on a paid feature. RRF is done **manually in
  Python** (see DECISIONS #1). Reranking is a **local** cross-encoder, never Elastic's
  `text_similarity_reranker`. The API logs the license tier at startup (Phase 2).
- **Never delete a live index.** Write to `emails-vN`, verify count + a smoke query, then
  flip the `emails` alias. Reindex to a new version; never drop the serving index.
- **Never commit** `data/`, model weights, `certs/`, or `.env` (all gitignored).
- **No hardcoded `localhost`/credentials.** All config via `pydantic-settings` + `.env`
  (`api/app/config.py`, `ingest/ingest/config.py`). Password comes from `ELASTIC_PASSWORD`.
- **Don't invent ES APIs.** When unsure about a parameter/retriever/license tier, check the
  docs for 9.5.x and cite the page in a code comment.
- Prefer boring, explicit code over clever abstractions.

## Workflow
- Plan before coding each phase; list files to create/change; get approval.
- Small commits, **conventional commit messages** (`feat:`, `fix:`, `chore:`, `docs:`, ...).
- Quality gate before committing: `make lint && make typecheck && make test`.
- Keep `DECISIONS.md` updated: decision, alternatives, reason.

## Where things live
- Cluster: `docker-compose.yml` (profiles: default 3-node, `single`, `kibana`); helpers in
  `scripts/`. Mapping: `ingest/mappings/emails.json` (Phase 1). Ingest stages: `ingest/ingest/`.
- API: `api/app/` (`config.py`, `es.py`, `main.py`, `search/`, `routes/`).
- Tests: `*/tests/`; integration tests are marked `@pytest.mark.integration` and need ES.

## Commit attribution
End commit messages with the Co-Authored-By / Claude-Session lines provided by the session.
