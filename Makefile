# Ledger — developer entry points. Run `make help`.
SHELL := /bin/bash
COMPOSE := docker compose
UV := uv
.DEFAULT_GOAL := help

help:  ## Show available targets
	grep -E '^[a-zA-Z0-9_-]+:.*## ' $(MAKEFILE_LIST) | sed -E 's/:.*## /\t/' | sort | awk -F'\t' '{printf "  \033[36m%-16s\033[0m %s\n",$$1,$$2}'

preflight:  ## Check docker, disk, python, and .env
	scripts/preflight.sh

install:  ## Create the shared .venv and install all packages + dev tools
	$(UV) sync --all-packages --all-groups

up:  ## Start the 3-node cluster (waits for green) and export the CA cert
	scripts/preflight.sh
	$(COMPOSE) up -d --wait setup es01 es02 es03
	scripts/certs.sh
	echo "Cluster up. Run 'make health'."

up-single:  ## Start a single node (low RAM) and export the CA cert
	scripts/preflight.sh
	$(COMPOSE) --profile single up -d --wait es-single
	scripts/certs.sh

up-kibana:  ## Start Kibana (a cluster must already be up)
	$(COMPOSE) --profile kibana up -d kibana
	echo "Kibana on http://localhost:5601 (user: elastic)"

certs:  ## Export the CA cert to ./certs/ca.crt
	scripts/certs.sh

health:  ## Show cluster health + license tier
	scripts/health.sh

down:  ## Stop everything and remove volumes
	$(COMPOSE) --profile single --profile kibana down -v

ingest-dev:  ## Run the whole pipeline over the deterministic 10k dev subset
	$(UV) run python -m ingest.cli run --subset dev

ingest-full:  ## Run the whole pipeline over the entire corpus
	$(UV) run python -m ingest.cli run --subset full

spotcheck:  ## Compare 20 parsed documents against their raw maildir files
	$(UV) run python scripts/spotcheck.py

stats:  ## Print the per-stage ingestion stats
	@for f in data/stats/*.json; do echo "--- $$f"; cat $$f; done

eval-pool:  ## Build evaluation candidate pools and auto-grade what rules cover
	$(UV) run python -m eval.cli pool
	$(UV) run python -m eval.cli autolabel

eval-label:  ## Hand-label the conceptual queries (resumable)
	$(UV) run python -m eval.cli label

eval:  ## Measure every retrieval method and write eval/results/<date>.md
	$(UV) run python -m eval.cli run

eval-baseline:  ## Measure and update the committed baseline
	$(UV) run python -m eval.cli run --write-baseline

eval-check:  ## Fail if hybrid NDCG@10 regressed >2 points vs the baseline
	$(UV) run python -m eval.cli check

bench:  ## Measure search latency against a running API (p50/p95/p99)
	$(UV) run python -m ops.bench.cli run

chaos:  ## Kill a node under live load and report the success rate
	$(UV) run python -m ops.chaos.cli run

snapshot:  ## Snapshot the index behind the `emails` alias
	$(UV) run python -m ops.snapshots.cli snapshot

snapshots:  ## List snapshots in the repository
	$(UV) run python -m ops.snapshots.cli list

restore:  ## Restore SNAP=<name> into a NEW index version (never over the live one)
	@test -n "$(SNAP)" || { echo "usage: make restore SNAP=<snapshot-name>"; exit 2; }
	$(UV) run python -m ops.snapshots.cli restore $(SNAP)

lint:  ## ruff check
	$(UV) run ruff check .

format:  ## ruff format (write)
	$(UV) run ruff format .

format-check:  ## ruff format (check only)
	$(UV) run ruff format --check .

typecheck:  ## mypy
	$(UV) run mypy api/app ingest/ingest ops

test:  ## Fast unit tests (no ES)
	$(UV) run pytest -m "not integration"

test-integration:  ## Integration tests (needs Docker for testcontainers)
	$(UV) run pytest -m integration

test-all:  ## All tests
	$(UV) run pytest

web-install:  ## Install the frontend dependencies (web/)
	cd web && npm ci

web:  ## Run the frontend dev server on :3000
	cd web && npm run dev

web-build:  ## Production build of the frontend
	cd web && npm run build

web-check:  ## Typecheck the frontend
	cd web && npm run typecheck

.PHONY: bench chaos snapshot snapshots restore help preflight install up up-single up-kibana certs health down ingest-dev ingest-full spotcheck stats eval-pool eval-label eval eval-baseline eval-check lint format format-check typecheck test test-integration test-all
