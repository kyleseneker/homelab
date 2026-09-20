#!/usr/bin/env bash
#
# One-time Vault initialization for the homelab cluster.
#
# Prerequisites:
#   - kubectl configured with cluster access
#   - vault CLI installed (https://developer.hashicorp.com/vault/install)
#   - Vault pod running (deployed via Argo CD)
#
set -euo pipefail
umask 077

VAULT_NAMESPACE="${VAULT_NAMESPACE:-${VAULT_NS:-vault}}"
VAULT_POD="${VAULT_POD:-vault-0}"
VAULT_PORT="${VAULT_PORT:-8200}"
VAULT_KV_PATH="${VAULT_KV_PATH:-homelab}"
ESO_NAMESPACE="${ESO_NAMESPACE:-external-secrets}"
ESO_SA_NAME="${ESO_SA_NAME:-external-secrets}"
INIT_OUTPUT_FILE="${INIT_OUTPUT_FILE:-vault-init-keys.json}"

export VAULT_ADDR="http://127.0.0.1:${VAULT_PORT}"

info()  { echo "==> $*"; }
warn()  { echo "WARN: $*" >&2; }
error() { echo "ERROR: $*" >&2; exit 1; }

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
for tool in kubectl vault jq; do
  command -v "$tool" >/dev/null || error "Required tool missing: $tool"
done
if [[ "${1:-}" != "--connected" ]]; then
  export VAULT_NS="$VAULT_NAMESPACE" VAULT_POD VAULT_PORT
  exec "$ROOT/scripts/with-vault.sh" "$ROOT/scripts/vault-init.sh" --connected
fi

# -----------------------------------------------------------------------
# 2. Check initialization status and initialize if needed
# -----------------------------------------------------------------------
VAULT_INIT_JSON=$(vault status -format=json 2>/dev/null || true)
if ! printf '%s' "$VAULT_INIT_JSON" | jq -e '.initialized | type == "boolean"' >/dev/null; then
  error "Cannot read Vault initialization status; refusing to initialize."
fi
INIT_STATUS=$(printf '%s' "$VAULT_INIT_JSON" | jq -r '.initialized')

if [[ "$INIT_STATUS" == "false" ]]; then
  [[ ! -e "$INIT_OUTPUT_FILE" ]] || error "Refusing to overwrite existing $INIT_OUTPUT_FILE"
  info "Initializing Vault with one recovery share (AWS KMS auto-unseal)..."
  (set -o noclobber; vault operator init -recovery-shares=1 -recovery-threshold=1 -format=json > "$INIT_OUTPUT_FILE")
  info "Recovery key and root token saved privately to $INIT_OUTPUT_FILE (mode 0600)."
  info "Store them in your password manager, then remove the local file."

else
  info "Vault is already initialized."
fi

# -----------------------------------------------------------------------
# 3. Wait for Vault to be unsealed (auto-unseal via AWS KMS)
# -----------------------------------------------------------------------
# vault status exits 2 when sealed; capture output separately
VAULT_STATUS_JSON=$(vault status -format=json 2>/dev/null || true)
SEAL_TYPE=$(echo "$VAULT_STATUS_JSON" | jq -r '.type' 2>/dev/null || echo "unknown")
SEAL_STATUS=$(echo "$VAULT_STATUS_JSON" | jq -r '.sealed' 2>/dev/null || echo "true")

if [[ "$SEAL_STATUS" != "false" ]]; then
  if [[ "$SEAL_TYPE" == "awskms" ]]; then
    info "Vault is configured for AWS KMS auto-unseal. Waiting for auto-unseal to complete..."
    for i in $(seq 1 12); do
      sleep 5
      VAULT_STATUS_JSON=$(vault status -format=json 2>/dev/null || true)
      SEAL_STATUS=$(echo "$VAULT_STATUS_JSON" | jq -r '.sealed' 2>/dev/null || echo "true")
      if [[ "$SEAL_STATUS" == "false" ]]; then
        info "Vault is unsealed."
        break
      fi
      warn "Still sealed (attempt ${i}/12)..."
    done
    if [[ "$SEAL_STATUS" != "false" ]]; then
      error "Vault did not auto-unseal within 60 seconds. Check the vault-aws-kms Secret and KMS connectivity."
    fi
  else
    error "Vault is sealed. This should not occur with KMS auto-unseal — check the vault-aws-kms Secret and KMS connectivity."
  fi
else
  info "Vault is already unsealed."
fi

# -----------------------------------------------------------------------
# 4. Authenticate
# -----------------------------------------------------------------------
if [[ -z "${VAULT_TOKEN:-}" && -f "$INIT_OUTPUT_FILE" ]]; then
  VAULT_TOKEN=$(jq -er '.root_token | select(type == "string" and length > 0)' "$INIT_OUTPUT_FILE")
  export VAULT_TOKEN
fi
if ! vault token lookup >/dev/null 2>&1; then
  [[ -t 0 ]] || error "Set VAULT_TOKEN to a token authorized to configure Vault."
  read -rsp "Enter an administrative Vault token: " VAULT_TOKEN
  echo ""
  export VAULT_TOKEN
  vault token lookup >/dev/null || error "Vault authentication failed."
fi

# -----------------------------------------------------------------------
# 5. Enable KV v2 secrets engine
# -----------------------------------------------------------------------
if vault secrets list -format=json | jq -e ".\"${VAULT_KV_PATH}/\"" &>/dev/null; then
  info "KV v2 engine already enabled at ${VAULT_KV_PATH}/."
else
  info "Enabling KV v2 secrets engine at ${VAULT_KV_PATH}/..."
  vault secrets enable -path="$VAULT_KV_PATH" kv-v2
fi

# -----------------------------------------------------------------------
# 6. Enable Kubernetes auth method
# -----------------------------------------------------------------------
if vault auth list -format=json | jq -e '.["kubernetes/"]' &>/dev/null; then
  info "Kubernetes auth method already enabled."
else
  info "Enabling Kubernetes auth method..."
  vault auth enable kubernetes
fi

# -----------------------------------------------------------------------
# 7. Configure Kubernetes auth method
# -----------------------------------------------------------------------
info "Configuring Kubernetes auth method..."
vault write auth/kubernetes/config \
  kubernetes_host="https://kubernetes.default.svc:443"

# -----------------------------------------------------------------------
# 8. Create ESO read policy
# -----------------------------------------------------------------------
info "Writing external-secrets-read policy..."
vault policy write external-secrets-read - <<POLICY
path "${VAULT_KV_PATH}/data/*" {
  capabilities = ["read"]
}
path "${VAULT_KV_PATH}/metadata/*" {
  capabilities = ["read", "list"]
}
POLICY

# -----------------------------------------------------------------------
# 9. Create ESO role bound to the ESO service account
# -----------------------------------------------------------------------
info "Creating external-secrets Vault role..."
vault write auth/kubernetes/role/external-secrets \
  bound_service_account_names="$ESO_SA_NAME" \
  bound_service_account_namespaces="$ESO_NAMESPACE" \
  policies=external-secrets-read \
  ttl=1h

# -----------------------------------------------------------------------
# Done
# -----------------------------------------------------------------------
echo ""
info "Vault initialization complete."
info ""
info "Next steps:"
info "  1. Store the root token in your password manager"
info "  2. Delete ${INIT_OUTPUT_FILE} if it exists (DO NOT commit it)"
info "  3. Store recovery keys separately; they cannot replace the KMS key during recovery"
info "  4. Populate secrets with: make vault-put-secret SECRET_PATH=<path> KEY=<key> (export VAL)"
info "  5. Verify ClusterSecretStore: kubectl get clustersecretstore vault-backend"
