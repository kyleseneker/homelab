# Secret Rotation

This runbook covers procedures for rotating application secrets using Vault and External Secrets Operator.

## Standard Secret Rotation

Use this procedure to rotate any application secret (API keys, credentials, passwords).

1. Connect to Vault:

    ```bash
    kubectl port-forward -n vault svc/vault 8200:8200
    export VAULT_ADDR=http://127.0.0.1:8200
    vault login  # enter root token
    ```

2. Update the secret in Vault:

    ```bash
    vault kv put homelab/<path> key1=new_value key2=new_value
    ```

    For example, to rotate the MinIO password:

    ```bash
    vault kv put homelab/infrastructure/minio \
      rootUser=minioadmin \
      rootPassword=new_secure_password
    ```

3. Wait for ESO to sync (default: 1 hour), or force an immediate sync:

    ```bash
    kubectl annotate externalsecret -n <namespace> <name> \
      force-sync=$(date +%s) --overwrite
    ```

4. Verify the secret was updated:

    ```bash
    kubectl get externalsecret -n <namespace> <name>
    # STATUS should show "SecretSynced"
    ```

Pods referencing the secret will pick up the new values on their next restart. The Reloader controller automatically restarts pods when their referenced secrets change.

!!! tip
    To update a single key without overwriting the entire secret, use `vault kv patch`:

    ```bash
    vault kv patch homelab/infrastructure/minio rootPassword=new_password
    ```

## Secret Inventory

All secrets managed in this cluster, their Vault paths, and target namespaces:

| Secret | Namespace | Vault Path |
|--------|-----------|------------|
| `vpn-credentials` | `arr` | `homelab/apps/vpn` |
| `recyclarr-secrets` | `arr` | `homelab/apps/recyclarr` |
| `exportarr-secrets` | `arr` | `homelab/apps/exportarr` |
| `unpackerr-secrets` | `arr` | `homelab/apps/unpackerr` |
| `homepage-secrets` | `arr` | `homelab/apps/homepage` |
| `grafana-admin` | `monitoring` | `homelab/infrastructure/grafana` |
| `grafana-oidc-secret` | `monitoring` | `homelab/infrastructure/grafana-oidc` |
| `alertmanager-slack-webhook` | `monitoring` | `homelab/infrastructure/alertmanager-slack` |
| `minio-credentials` | `backups` | `homelab/infrastructure/minio` |
| `velero-cloud-credentials` | `backups` | `homelab/infrastructure/velero` |
| `authentik-credentials` | `auth` | `homelab/infrastructure/authentik` |
| `argocd-secret` | `argocd` | `homelab/infrastructure/argocd-oidc` |

!!! note
    All Vault paths are relative to the `homelab` KV v2 mount. The `*-external-secret.yml` manifests in `k8s/clusters/homelabk8s01/` document the specific keys for each secret.
