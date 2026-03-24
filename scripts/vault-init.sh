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

VAULT_NAMESPACE="${VAULT_NAMESPACE:-vault}"
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

cleanup() {
  if [[ -n "${PORT_FORWARD_PID:-}" ]]; then
    kill "$PORT_FORWARD_PID" 2>/dev/null || true
    wait "$PORT_FORWARD_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT

# -----------------------------------------------------------------------
# 1. Port-forward to Vault
# -----------------------------------------------------------------------
info "Starting port-forward to ${VAULT_POD} in namespace ${VAULT_NAMESPACE}..."
kubectl port-forward -n "$VAULT_NAMESPACE" "pod/${VAULT_POD}" "${VAULT_PORT}:8200" &
PORT_FORWARD_PID=$!
sleep 3

if ! kill -0 "$PORT_FORWARD_PID" 2>/dev/null; then
  error "Port-forward failed. Is the Vault pod running?"
fi

# -----------------------------------------------------------------------
# 2. Check initialization status and initialize if needed
# -----------------------------------------------------------------------
VAULT_INIT_JSON=$(vault status -format=json 2>/dev/null || true)
INIT_STATUS=$(echo "$VAULT_INIT_JSON" | jq -r '.initialized' 2>/dev/null || echo "false")

if [[ "$INIT_STATUS" == "false" ]]; then
  info "Initializing Vault (1 key share, 1 key threshold)..."
  vault operator init -key-shares=1 -key-threshold=1 -format=json > "$INIT_OUTPUT_FILE"

  UNSEAL_KEY=$(jq -r '.unseal_keys_b64[0]' "$INIT_OUTPUT_FILE")
  ROOT_TOKEN=$(jq -r '.root_token' "$INIT_OUTPUT_FILE")

  echo ""
  echo "============================================================"
  echo "  VAULT INITIALIZED"
  echo ""
  echo "  Unseal Key:  ${UNSEAL_KEY}"
  echo "  Root Token:  ${ROOT_TOKEN}"
  echo ""
  echo "  These credentials are saved to: ${INIT_OUTPUT_FILE}"
  echo "  Store them in your password manager, then delete the file."
  echo "  DO NOT commit this file to git."
  echo "============================================================"
  echo ""
else
  info "Vault is already initialized."
fi

# -----------------------------------------------------------------------
# 3. Wait for Vault to be unsealed (auto-unseal via AWS KMS)
# -----------------------------------------------------------------------
# vault status exits 2 when sealed; capture output separately
VAULT_STATUS_JSON=$(vault status -format=json 2>/dev/null || true)
SEAL_TYPE=$(echo "$VAULT_STATUS_JSON" | jq -r '.seal_type' 2>/dev/null || echo "unknown")
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
    error "Vault is sealed. If you are in the pre-migration window, run 'make vault-unseal'. After KMS migration, this should not occur — check the vault-aws-kms Secret and KMS configuration."
  fi
else
  info "Vault is already unsealed."
fi

# -----------------------------------------------------------------------
# 4. Authenticate
# -----------------------------------------------------------------------
if [[ -f "$INIT_OUTPUT_FILE" ]]; then
  ROOT_TOKEN=$(jq -r '.root_token' "$INIT_OUTPUT_FILE")
  vault login -no-print "$ROOT_TOKEN"
else
  SEAL_STATUS=$(vault status -format=json 2>/dev/null | jq -r '.sealed' 2>/dev/null || echo "true")
  if [[ "$SEAL_STATUS" == "false" ]]; then
    if ! vault token lookup &>/dev/null; then
      echo -n "Enter root token: "
      read -rs ROOT_TOKEN
      echo ""
      vault login -no-print "$ROOT_TOKEN"
    fi
  fi
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
info "  3. If Vault is still using Shamir sealing, store the unseal key and follow the KMS migration runbook: docs/runbooks/vault-kms-migration.md"
info "  4. Populate secrets with: vault kv put ${VAULT_KV_PATH}/<path> key=value"
info "  5. Verify ClusterSecretStore: kubectl get clustersecretstore vault-backend"
