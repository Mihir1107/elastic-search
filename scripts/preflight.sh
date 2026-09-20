#!/usr/bin/env bash
# Preflight checks for Ledger: docker, disk, python, .env.
set -uo pipefail
rc=0
echo "== Ledger preflight =="

if [ ! -f .env ]; then
  cp .env.example .env
  echo "• created .env from .env.example (CHANGE THE PASSWORDS before real use)"
else
  echo "• .env present"
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
