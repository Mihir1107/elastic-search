#!/usr/bin/env bash
# Print cluster health and the active license tier (kickoff §4).
set -euo pipefail
set -a; source .env; set +a
port="${ES_PORT:-9200}"
ca="${ES_CA_CERT:-./certs/ca.crt}"
echo "== cluster health =="
curl -s --cacert "${ca}" -u "elastic:${ELASTIC_PASSWORD}" "https://localhost:${port}/_cluster/health?pretty"
echo "== license =="
curl -s --cacert "${ca}" -u "elastic:${ELASTIC_PASSWORD}" "https://localhost:${port}/_license?pretty"
