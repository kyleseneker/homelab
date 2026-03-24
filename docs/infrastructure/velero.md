# Velero

Velero provides backup and restore capabilities for Kubernetes resources and persistent volume data.

## Details

| Field | Value |
|-------|-------|
| Chart | `velero` |
| Repository | <https://vmware-tanzu.github.io/helm-charts> |
| Version | 12.0.0 |
| Namespace | `backups` (CreateNamespace=true) |
| Sync Wave | -1 |

## Key Configuration

### S3 Backend (MinIO)

- **Plugin**: `velero/velero-plugin-for-aws:v1.14.0` (provides S3 compatibility)
- **Endpoint**: `http://minio.backups.svc.cluster.local:9000`
- **Bucket**: `velero`
- **Region**: `minio`
- **s3ForcePathStyle**: `true`
- **Credentials**: Sourced from the ExternalSecret `velero-cloud-credentials` (synced from Vault)

### Volume Backup

- **Default method**: File system backup via Kopia (`defaultVolumesToFsBackup: true`)
- **Node agent**: Deployed as a DaemonSet on every node to handle file-system-level volume snapshots

### Backup Schedules

| Schedule | Cron | Scope | TTL |
|----------|------|-------|-----|
| `daily-stateful` | 3:00 AM daily | `arr` + `monitoring` namespaces | 7 days |
| `weekly-full-cluster` | 4:00 AM Sunday | All namespaces except `kube-system`, `kube-public` | 30 days |

### Resources

| Component | CPU Request | Memory Request | Memory Limit |
|-----------|-------------|----------------|--------------|
| Server | 100m | 128Mi | 512Mi |
| Node Agent | 100m | 128Mi | 1Gi |

## Cluster Integration

Velero depends on MinIO (wave -2) for its backup storage location and deploys at sync wave -1. The backup workflow is:

1. Velero server creates a backup according to the defined schedules.
2. Kubernetes resource manifests are serialized and stored in the MinIO `velero` bucket.
3. The node agent (DaemonSet) handles file-system-level backup of PersistentVolume data using Kopia.
4. Both resource manifests and volume data are stored in MinIO, which persists to NFS.

!!! warning "Restore Prerequisites"
    After a full cluster rebuild, MinIO and Vault must be restored before Velero can access its backup data. Ensure the Vault unseal key is stored outside the cluster (e.g., in a password manager).

## Upstream Documentation

<https://velero.io>
