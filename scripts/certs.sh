#!/usr/bin/env bash
# Copy the CA cert generated inside the cluster out to ./certs/ca.crt so the
# host-side Python clients and curl can verify TLS.
set -euo pipefail
mkdir -p certs
cid=$(docker compose ps -q es01 2>/dev/null || true)
if [ -z "${cid}" ]; then cid=$(docker compose ps -q es-single 2>/dev/null || true); fi
if [ -z "${cid}" ]; then
  echo "No ES container running; run 'make up' (or 'make up-single') first." >&2
  exit 1
fi
docker cp "${cid}:/usr/share/elasticsearch/config/certs/ca/ca.crt" ./certs/ca.crt
chmod 644 ./certs/ca.crt
echo "Wrote ./certs/ca.crt"
