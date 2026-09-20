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

lint:  ## ruff check
	$(UV) run ruff check .

format:  ## ruff format (write)
	$(UV) run ruff format .

format-check:  ## ruff format (check only)
	$(UV) run ruff format --check .

typecheck:  ## mypy
	$(UV) run mypy api/app ingest/ingest

test:  ## Fast unit tests (no ES)
	$(UV) run pytest -m "not integration"

test-integration:  ## Integration tests (needs Docker for testcontainers)
	$(UV) run pytest -m integration

test-all:  ## All tests
	$(UV) run pytest

.PHONY: help preflight install up up-single up-kibana certs health down lint format format-check typecheck test test-integration test-all
