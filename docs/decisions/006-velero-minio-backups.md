# ADR-006: Velero + MinIO for Backup and Restore

## Status

Accepted

## Context

The cluster needs a backup strategy that covers both Kubernetes resource manifests and persistent volume data. Backups must survive a full cluster rebuild and support selective restoration.

## Decision

Use Velero with the AWS plugin for backup orchestration, Kopia for file-system PVC backup, and a standalone MinIO instance as the S3-compatible backup target. MinIO stores its data on an NFS-backed PVC.

## Alternatives Considered

- **NFS snapshots only**: Covers data but not Kubernetes resource state (Secrets, ConfigMaps, RBAC). Restoration requires manual re-creation of all cluster resources.
- **Restic/Kopia standalone**: Can back up PVC data but doesn't handle Kubernetes resource backup or provide integration with `kubectl`-style restore workflows.
- **Cloud S3 (AWS, Backblaze B2)**: Durable off-site storage but adds ongoing cost and external dependency. Could be used as a secondary target in the future.
- **Longhorn/Rook volume snapshots**: Require distributed storage (see ADR-005). Not applicable with NFS.

## Rationale

- **In-cluster S3**: MinIO provides S3-compatible storage without cloud dependency. Velero's AWS plugin works unmodified against MinIO.
- **Resource + data**: Velero backs up both Kubernetes manifests and PVC data (via Kopia file-system backup), providing a complete cluster snapshot.
- **NFS data survival**: MinIO stores to an NFS-backed PVC with Retain policy. Backup data persists on the NAS across cluster rebuilds.
- **Dual schedules**: Daily backups (arr, monitoring, auth namespaces, 7-day retention) catch frequent changes. Weekly full-cluster backups (30-day retention) provide broader coverage.
- **Selective restore**: Velero supports namespace-scoped and resource-scoped restores, allowing targeted recovery without affecting the rest of the cluster.

## Consequences

- MinIO is a single standalone instance. Backup data has the same NAS SPOF as application data. For true off-site durability, a cloud S3 target could be added as a secondary BackupStorageLocation.
- Velero restore recreates resources but may conflict with ArgoCD's desired state. After restore, ArgoCD sync should be verified.
- The `vault-aws-kms` Secret is not backed up by Velero (it must be manually created before Vault can start). This is documented in the disaster recovery runbook.
