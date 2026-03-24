# Secret Management

This document covers the External Secrets Operator (ESO) workflow used to sync secrets from HashiCorp Vault into Kubernetes, the architecture, and disaster recovery considerations.

## Overview

Secrets are managed by [External Secrets Operator](https://external-secrets.io/) syncing from [HashiCorp Vault](https://www.vaultproject.io/). Vault stores all secret values in a KV v2 engine, and ESO pulls them into Kubernetes as native `Secret` objects on a configurable refresh interval.

```mermaid
flowchart LR
    operator["Operator"] -->|"vault kv put"| vault["HashiCorp Vault\n(KV v2 engine)"]
    vault -->|"K8s auth"| eso["External Secrets\nOperator"]
    eso -->|"creates / syncs"| secret["K8s Secret\n(cluster-only)"]
    secret --> app["Application Pod"]
```

### How It Works

1. Secrets are stored in Vault under the `homelab/` KV v2 mount
2. A `ClusterSecretStore` connects ESO to Vault using Kubernetes auth (no static tokens)
3. `ExternalSecret` resources in each namespace declare which Vault path and keys to sync
4. ESO periodically fetches values from Vault and creates or updates the corresponding K8s `Secret`
5. Pods consume the secrets as environment variables or volume mounts, as with any Kubernetes Secret

## Components

| Component | Namespace | Purpose |
|-----------|-----------|---------|
| Vault | `vault` | Secrets backend (KV v2 engine, standalone mode, file storage) |
| External Secrets Operator | `external-secrets` | Syncs Vault secrets into K8s Secret objects |
| ClusterSecretStore | `external-secrets` | Cluster-wide connection config for Vault |
| ExternalSecret | Various | Per-secret declaration of what to sync from Vault |

## Vault Path Structure

All secrets live under the `homelab` KV v2 mount, organized by layer:

| Vault Path | K8s Secret | Namespace |
|------------|------------|-----------|
| `infrastructure/minio` | `minio-credentials` | `backups` |
| `infrastructure/velero` | `velero-cloud-credentials` | `backups` |
| `infrastructure/authentik` | `authentik-credentials` | `auth` |
| `infrastructure/argocd-oidc` | `argocd-secret` (merge) | `argocd` |
| `infrastructure/grafana` | `grafana-admin` | `monitoring` |
| `infrastructure/grafana-oidc` | `grafana-oidc-secret` | `monitoring` |
| `infrastructure/alertmanager-slack` | `alertmanager-slack-webhook` | `monitoring` |
| `apps/vpn` | `vpn-credentials` | `arr` |
| `apps/recyclarr` | `recyclarr-secrets` | `arr` |
| `apps/exportarr` | `exportarr-secrets` | `arr` |
| `apps/unpackerr` | `unpackerr-secrets` | `arr` |
| `apps/homepage` | `homepage-secrets` | `arr` |

## Workflow

### Adding or Updating a Secret

```mermaid
flowchart TD
    writeVault["1. Write secret to Vault\nvault kv put homelab/path key=value"] --> esoSync["2. ESO syncs on next interval\n(default: 1 hour)"]
    esoSync --> secretCreated["3. K8s Secret created/updated"]
    secretCreated --> reloader["4. Reloader restarts pods\n(if annotated)"]
```

```bash
# Port-forward to Vault (or use ingress at vault.homelab.local)
kubectl port-forward -n vault svc/vault 8200:8200

# Write or update a secret
vault kv put homelab/infrastructure/minio \
  rootUser=minioadmin \
  rootPassword=new_password

# Force an immediate sync (optional, otherwise waits for refreshInterval)
kubectl annotate externalsecret -n backups minio-credentials \
  force-sync=$(date +%s) --overwrite
```

### Adding a Secret for a New Application

1. Create an `ExternalSecret` YAML referencing a Vault path
2. Write the values into Vault at that path
3. Commit the `ExternalSecret` YAML and push -- ArgoCD syncs it
4. ESO creates the K8s Secret automatically

See the [adding an app runbook](../runbooks/adding-an-app.md) for the full workflow.

## Secret Rotation

Rotating a secret no longer requires re-sealing or Git commits:

```bash
# Update a single key (preserves other keys at the same path)
vault kv patch homelab/apps/vpn OPENVPN_PASSWORD=new_password

# Or replace all keys at a path (omitted keys are deleted)
vault kv put homelab/apps/vpn \
  OPENVPN_USER=new_user \
  OPENVPN_PASSWORD=new_password

# ESO picks up the change at the next refresh interval (1h default)
# Reloader automatically restarts affected pods
```

!!! warning
    `vault kv put` replaces **all** keys at a path. If you only specify one key, any other keys at that path are deleted. Use `vault kv patch` to update individual keys safely.

For immediate rotation, annotate the ExternalSecret to force a sync:

```bash
kubectl annotate externalsecret -n arr vpn-credentials \
  force-sync=$(date +%s) --overwrite
```

## Disaster Recovery

### Vault Backup

Vault data is stored on a PVC backed by NFS. Velero backs up all PVCs on schedule, so Vault data is included in cluster backups.

### Vault Unsealing

After a Vault pod restart, manual unsealing is required:

```bash
make vault-unseal
```

Store the unseal key and root token securely in a password manager.

### Cluster Rebuild

When rebuilding the cluster from scratch:

1. Deploy Vault and ESO via ArgoCD (automatic from Git)
2. Restore Vault data from Velero backup, or re-initialize with `make vault-init`
3. If re-initializing, re-populate all secrets from their original sources
4. ESO automatically creates all K8s Secrets once Vault is available
