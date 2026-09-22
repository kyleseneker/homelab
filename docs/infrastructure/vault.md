# HashiCorp Vault

HashiCorp Vault provides centralized secrets storage for the cluster. All application and infrastructure secrets are stored in Vault's KV v2 engine and synced to Kubernetes by the External Secrets Operator.

## Details

| Field | Value |
|-------|-------|
| Chart | `vault` |
| Repository | <https://helm.releases.hashicorp.com> |
| Version | 0.32.0 |
| Namespace | `vault` |

## Key Configuration

- **Mode**: Integrated Raft (one voter; not highly available)
- **Storage**: Local-path PVC `vault-raft-data` (1Gi; protected from Argo pruning)
- **Seal**: AWS KMS auto-unseal (key: `alias/vault-unseal-homelab`)
- **UI**: Enabled at `vault.homelab.local`
- **Injector**: Disabled (using External Secrets Operator instead)
- **Resources**:
    - Requests: 50m CPU, 64Mi memory
    - Limits: 256Mi memory

## Initialization

A new, empty Vault requires one-time initialization after first deployment. Never
initialize migrated data; use the recovery runbook for snapshot restoration:

```bash
make vault-init
```

This runs `scripts/vault-init.sh`, which:

1. Waits for Vault to auto-unseal via AWS KMS
2. Enables the `homelab` KV v2 secrets engine
3. Enables Kubernetes auth method
4. Creates an ESO read policy and role

Then run `scripts/vault-snapshot-auth.sh` with an administrative Vault CLI session
to configure the read-only backup role. Repeat this after rebuilding auth bindings.

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

Vault, cert-manager, and the External Secrets Operator form the bootstrap layer everything else depends on. ESO authenticates to Vault using the Kubernetes auth method -- the ESO service account token is validated against the cluster API server, so no static credentials are needed.

!!! info "Internal traffic is plaintext"
    Vault's listener runs with `tls_disable = 1` inside the cluster. External access goes through the ingress (TLS-terminated by cert-manager), but pod-to-pod traffic between ESO and Vault is unencrypted HTTP. This is a deliberate homelab simplification -- all traffic stays within the cluster network.

## Backup

`CronJob/vault-snapshot` saves a native online snapshot daily at **01:30 UTC** and
uploads it to `s3://velero-offsite-homelab/vault-raft-snapshots/`. It succeeds only
after downloading the object and matching its version and SHA-256. The projected
service-account identity has only snapshot-read access; AWS credentials come
through ESO from the existing Velero offsite credential. No root token or
Kubernetes administration is granted to the job.

Current objects expire after 30 days; noncurrent versions follow the existing
90-day bucket rule. `VaultSnapshotStale` alerts after 30 hours without a successful
job (plus 30 minutes pending). The daily interval is not an agreed RPO/RTO.

The production snapshot passed an isolated S3 restore using independently exported
HCP credentials, the original KMS key and original Vault administrative token.
See [native snapshot recovery](../runbooks/backup-and-restore.md#production-native-snapshots)
and [ADR-024](../decisions/024-vault-integrated-storage.md).

The old `data-vault-0` NFS claim is retained as pre-cutover recovery material. It
receives no new writes and cannot provide a current rollback. One local Raft voter
still requires snapshot recovery after node/storage loss; three-voter HA remains
planned. Do not increase replicas against the single shared claim.

### Consistent file-backend copy

This is the legacy file-backend procedure. The helper refuses the current Raft
backend; retain it for old archives and file-stage recovery.

`scripts/vault-file-backup.py` creates an encrypted archive while the standalone
Vault writer is stopped. It checks initialized/unsealed state, starts a read-only
reader on the same node, pauses the Vault Application, scales Vault to zero, and
validates the archive before publishing it with private permissions. Cleanup
restarts Vault, checks KMS auto-unseal and the original cluster identity, then
resumes reconciliation and removes the reader. Existing Kubernetes Secrets remain
available while Vault is down; Vault API requests and ESO refreshes cannot succeed
during that interval.

The ApplicationSet must preserve `argocd.argoproj.io/skip-reconcile`; otherwise it
removes the pause annotation and self-heal can restart the writer mid-copy. The
helper refuses to run without that prerequisite. Preserving the annotation does
not pause any application by itself. Remove every maintenance pause explicitly
when work is complete. See [Argo CD's preserved fields documentation](https://argo-cd.readthedocs.io/en/stable/operator-manual/applicationset/Controlling-Resource-Modification/).

Run from the repository root with cluster-admin access during a maintenance window:

```bash
mkdir -p .lab/vault-restore
chmod 700 .lab/vault-restore
python3 scripts/vault-file-backup.py --kubeconfig kubeconfig \
  --output .lab/vault-restore/vault-file-backup.tar.gz
```

The output must not already exist. Keep it encrypted and outside Git. This helper
creates a local recovery copy; it does not replace scheduled backups. Use the
[offsite transfer helper](../runbooks/backup-and-restore.md#offsite-vault-archive)
to upload and verify it. Manual local and S3 restores passed KMS auto-unseal and
authenticated secret-read checks. Production now uses the native snapshot job above.

If the process is forcibly killed, connectivity is lost, or restart verification
fails, inspect the cluster before retrying. Restore one Vault replica, wait for
`vault-0` to become Ready, and confirm initialized/unsealed state and the original
cluster identity. Only then remove the maintenance annotation and unused
`vault-file-backup-*` reader pod:

```bash
kubectl --kubeconfig kubeconfig -n vault scale statefulset/vault --replicas=1
kubectl --kubeconfig kubeconfig -n vault wait --for=create pod/vault-0 --timeout=120s
kubectl --kubeconfig kubeconfig -n vault wait --for=condition=Ready pod/vault-0 --timeout=180s
kubectl --kubeconfig kubeconfig -n vault exec vault-0 -- vault status
kubectl --kubeconfig kubeconfig -n argocd annotate application vault \
  argocd.argoproj.io/skip-reconcile-
```

Do not initialize Vault or modify its original data directory during recovery.
Delete incomplete local `.vault-backup-*` files after production is healthy.

## Upstream Documentation

<https://developer.hashicorp.com/vault/docs>
