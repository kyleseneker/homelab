#!/usr/bin/env bash
# Configure the production snapshot identity after Raft migration or recovery.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ "${1:-}" != "--connected" ]]; then
  exec "$ROOT/scripts/with-vault.sh" "$ROOT/scripts/vault-snapshot-auth.sh" --connected
fi
vault status -format=json | jq -e '.initialized and (.sealed == false) and (.storage_type == "raft")' >/dev/null
vault policy write vault-snapshot - <<'POLICY'
path "sys/storage/raft/snapshot" {
  capabilities = ["read"]
}
POLICY
vault write auth/kubernetes/role/vault-snapshot \
  bound_service_account_names=vault-snapshot \
  bound_service_account_namespaces="${VAULT_NS:-vault}" \
  audience=vault \
  token_policies=vault-snapshot \
  token_ttl=10m \
  token_max_ttl=10m
