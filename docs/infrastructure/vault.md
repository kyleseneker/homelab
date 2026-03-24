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
- **Seal**: AWS KMS auto-unseal (key: `alias/vault-unseal-homelab`)
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

1. Waits for Vault to auto-unseal via AWS KMS
2. Enables the `homelab` KV v2 secrets engine
3. Enables Kubernetes auth method
4. Creates an ESO read policy and role

Store the root token in a password manager.

!!! warning "Bootstrap dependency"
    The `vault-aws-kms` Kubernetes Secret must exist in the `vault` namespace before the Vault pod starts. See the [disaster recovery runbook](../runbooks/disaster-recovery.md#complete-cluster-rebuild) for the bootstrap procedure.

## Unsealing

Vault auto-unseals via AWS KMS on every pod restart. No manual intervention is required.

The KMS key and IAM credentials are provisioned with Terraform (`make aws-apply`) and stored as a manually-created Kubernetes Secret (`vault-aws-kms` in the `vault` namespace). This Secret is never committed to Git and must be recreated after a full cluster rebuild — see the [disaster recovery runbook](../runbooks/disaster-recovery.md#complete-cluster-rebuild).

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
