# ADR-013: Velero + MinIO for Backup and Restore

## Status

Accepted (updated 2026-03-28: added offsite backup to AWS S3)

## Context

The cluster needs a backup strategy that covers both Kubernetes resource manifests and persistent volume data. Backups must survive a full cluster rebuild and support selective restoration. The 3-2-1 backup rule requires at least one offsite copy to protect against site-level disasters.

## Decision

Use Velero with the AWS plugin for backup orchestration, Kopia for file-system PVC backup, and two storage targets:

1. **Local (MinIO)**: Standalone MinIO on an NFS-backed PVC for fast daily and weekly backups.
2. **Offsite (AWS S3)**: S3 bucket (`velero-offsite-homelab`) in us-east-1 for weekly offsite backups.

## Alternatives Considered

- **NFS snapshots only**: Covers data but not Kubernetes resource state (Secrets, ConfigMaps, RBAC). Restoration requires manual re-creation of all cluster resources.
- **Restic/Kopia standalone**: Can back up PVC data but doesn't handle Kubernetes resource backup or provide integration with `kubectl`-style restore workflows.
- **Backblaze B2**: Cheaper storage ($0.006/GB/month) but adds another vendor dependency. AWS was chosen because the account and IAM infrastructure already exist for Vault KMS auto-unseal.
- **Longhorn/Rook volume snapshots**: Require distributed storage (see ADR-006). Not applicable with NFS.

## Rationale

- **In-cluster S3**: MinIO provides S3-compatible storage without cloud dependency. Velero's AWS plugin works unmodified against MinIO.
- **Resource + data**: Velero backs up both Kubernetes manifests and PVC data (via Kopia file-system backup), providing a complete cluster snapshot.
- **NFS data survival**: MinIO stores to an NFS-backed PVC with Retain policy. Backup data persists on the NAS across cluster rebuilds.
- **Three schedules**: Daily backups (arr, monitoring, auth namespaces, 7-day retention) catch frequent changes. Weekly full-cluster backups (30-day retention) provide broader coverage. Weekly offsite backups (30-day retention) protect against site-level disaster.
- **AWS S3 Standard-IA**: Objects start in S3 Standard and transition to Standard-IA after 30 days via lifecycle policy. At ~$0.63/month for 50 GB, cost is negligible. Noncurrent versions expire after 90 days.
- **Selective restore**: Velero supports namespace-scoped and resource-scoped restores, allowing targeted recovery without affecting the rest of the cluster.
- **Reuse existing AWS account**: The AWS account, IAM patterns, and Terraform module already exist for Vault KMS. Adding an S3 bucket and IAM user follows the same pattern with minimal new infrastructure.

## Consequences

- Offsite backups add a runtime dependency on AWS S3 availability and internet egress from the cluster. Cilium network policy allows HTTPS egress (0.0.0.0/0:443) from the backups namespace.
- AWS credentials for the offsite IAM user are stored in Vault at `infrastructure/velero-offsite` and synced via ExternalSecret. During a DR rebuild where Vault is not yet available, the credentials must be manually created from values stored in a password manager.
- Velero restore recreates resources but may conflict with ArgoCD's desired state. After restore, ArgoCD sync should be verified.
- The `vault-aws-kms` Secret is not backed up by Velero (it must be manually created before Vault can start). This is documented in the disaster recovery runbook.
- Estimated monthly cost: ~$1 (S3 storage + PUT/GET requests).
