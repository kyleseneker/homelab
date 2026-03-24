# HashiCorp Vault

HashiCorp Vault provides centralized secrets storage for the cluster. All application and infrastructure secrets are stored in Vault's KV v2 engine and synced to Kubernetes by the External Secrets Operator.

## Details

| Field | Value |
|-------|-------|
| Chart | `vault` |
| Repository | <https://helm.releases.hashicorp.com> |
| Version | 0.32.0 |
| Namespace | `vault` |
| Sync Wave | -3 |

## Key Configuration

- **Mode**: Standalone (single replica, file storage)
- **Storage**: File backend on NFS-backed PVC (1Gi)
- **UI**: Enabled at `vault.homelab.local`
- **Injector**: Disabled (using External Secrets Operator instead)
- **Resources**:
    - Requests: 50m CPU, 64Mi memory
    - Limits: 256Mi memory

## Initialization

Vault requires one-time initialization after first deployment:

```bash
make vault-init
```

This runs `scripts/vault-init.sh`, which:

1. Initializes Vault with a single unseal key
2. Unseals the vault
3. Enables the `homelab` KV v2 secrets engine
4. Enables Kubernetes auth method
5. Creates an ESO read policy and role

Store the unseal key and root token in a password manager.

## Unsealing

Vault must be unsealed after every pod restart:

```bash
make vault-unseal
```

## Vault Path Structure

Secrets are organized under the `homelab` KV v2 mount:

- `infrastructure/` -- platform component secrets (MinIO, Velero, Authentik, Grafana, etc.)
- `apps/` -- application secrets (VPN, Recyclarr, Exportarr, Homepage, etc.)

## Cluster Integration

Vault deploys at sync wave -3 alongside cert-manager and the External Secrets Operator. ESO authenticates to Vault using the Kubernetes auth method -- the ESO service account token is validated against the cluster API server, so no static credentials are needed.

!!! info "Internal traffic is plaintext"
    Vault's listener runs with `tls_disable = 1` inside the cluster. External access goes through the ingress (TLS-terminated by cert-manager), but pod-to-pod traffic between ESO and Vault is unencrypted HTTP. This is a deliberate homelab simplification -- all traffic stays within the cluster network.

## Backup

Vault data lives on an NFS-backed PVC. Velero backs up all PVCs on schedule, covering Vault's file storage automatically.

## Upstream Documentation

<https://developer.hashicorp.com/vault/docs>
