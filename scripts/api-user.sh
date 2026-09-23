#!/usr/bin/env bash
# Create (or rotate) the least-privilege Elasticsearch user the search API runs
# as, and record its credentials in .env. The API then never holds the
# superuser password: a bug in it can read mail and write review tags, and
# nothing else -- no deleting indices, no touching users, no snapshots.
set -euo pipefail

[ -f .env ] || { echo "no .env; run 'make preflight' first" >&2; exit 1; }
set -a; source .env; set +a

host="${ES_HOST%%,*}"
user="${ES_API_USERNAME:-ledger_api}"
password="$(openssl rand -hex 24)"
tags_index="${TAGS_INDEX:-ledger-tags}"
alias_name="${EMAILS_ALIAS:-emails}"

es() {
  curl -sS --fail-with-body --cacert "${ES_CA_CERT:-./certs/ca.crt}" \
    -u "elastic:${ELASTIC_PASSWORD}" -H 'content-type: application/json' "$@"
}

es -X PUT "${host}/_security/role/ledger_api" -d @- >/dev/null <<JSON
{
  "cluster": ["monitor"],
  "indices": [
    {"names": ["${alias_name}", "${alias_name}-*"], "privileges": ["read", "view_index_metadata"]},
    {"names": ["${tags_index}"], "privileges": ["read", "write", "create_index", "manage"]}
  ]
}
JSON

es -X PUT "${host}/_security/user/${user}" -d @- >/dev/null <<JSON
{"password": "${password}", "roles": ["ledger_api"], "full_name": "Ledger search API"}
JSON

# Replace any previous values rather than appending duplicates.
tmp="$(mktemp)"
grep -v -E '^(ES_API_USERNAME|ES_API_PASSWORD)=' .env > "${tmp}" || true
printf 'ES_API_USERNAME=%s\nES_API_PASSWORD=%s\n' "${user}" "${password}" >> "${tmp}"
mv "${tmp}" .env
chmod 600 .env
echo "API user '${user}' ready (role ledger_api); credentials written to .env"
