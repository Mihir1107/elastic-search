#!/usr/bin/env bash
# Preflight checks for Ledger: docker, disk, python, .env.
set -uo pipefail
rc=0
echo "== Ledger preflight =="

if [ ! -f .env ]; then
  # Never start a cluster on the example passwords: generate real ones.
  sed -e "s/^ELASTIC_PASSWORD=.*/ELASTIC_PASSWORD=$(openssl rand -hex 16)/" \
      -e "s/^KIBANA_PASSWORD=.*/KIBANA_PASSWORD=$(openssl rand -hex 16)/" \
      .env.example > .env
  chmod 600 .env
  echo "• created .env from .env.example with generated passwords"
else
  echo "• .env present"
  if grep -qE '^(ELASTIC|KIBANA)_PASSWORD=changeme' .env; then
    # Only a warning: an existing cluster was bootstrapped with this password,
    # and changing .env alone would lock the clients out of it.
    echo "! .env still uses a default 'changeme' password. Rotate it with"
    echo "    POST /_security/user/elastic/_password, then update .env"
  fi
fi

if command -v uv >/dev/null 2>&1; then
  echo "• uv $(uv --version | awk '{print $2}')"
else
  echo "✗ uv not found — install from https://docs.astral.sh/uv/"; rc=1
fi

if uv python find 3.12 >/dev/null 2>&1; then
  echo "• python 3.12 available"
else
  echo "! python 3.12 not found (uv will fetch it on 'make install')"
fi

if docker info >/dev/null 2>&1; then
  echo "• docker daemon running"
else
  echo "✗ docker daemon NOT running — start Docker Desktop before 'make up'"; rc=1
fi

avail=$(df -Pg . 2>/dev/null | awk 'NR==2{print $4}')
if [ -n "${avail}" ]; then
  echo "• disk free: ${avail} GiB"
  if [ "${avail}" -lt 8 ]; then
    echo "! low disk (<8 GiB): OK for the 10k dev subset, risky for full-corpus (Phase 6)"
  fi
fi

if [ "${rc}" -eq 0 ]; then echo "preflight: OK"; else echo "preflight: FAILED"; fi
exit "${rc}"
