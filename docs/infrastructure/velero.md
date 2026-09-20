# Velero

Velero provides backup and restore capabilities for Kubernetes resources and persistent volume data.

## Details

| Field | Value |
|-------|-------|
| Chart | `velero` |
| Repository | <https://vmware-tanzu.github.io/helm-charts> |
| Version | 12.0.0 |
| Namespace | `backups` (CreateNamespace=true) |

## Key Configuration

### S3 Backend (MinIO)

- **Plugin**: `velero/velero-plugin-for-aws:v1.14.2` (provides S3 compatibility)
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
| `daily-stateful` | 03:00 UTC daily | `arr`, `monitoring`, `auth`, `openclaw` namespaces | 7 days |
| `weekly-full-cluster` | 04:00 UTC Sunday | All except `kube-system`, `kube-public`, `nfs-provisioner`, `backups` | 30 days |
| `weekly-offsite` | 05:00 UTC Sunday | `arr`, `monitoring`, `auth`, `openclaw`, `argocd`, `vault`, `external-secrets` | 30 days |

### Resources

| Component | CPU Request | Memory Request | Memory Limit |
|-----------|-------------|----------------|--------------|
| Server | 100m | 128Mi | 512Mi |
| Node Agent | 100m | 128Mi | 1Gi |

## Cluster Integration

Velero depends on MinIO for its default backup storage location. The backup workflow is:

1. Velero server creates a backup according to the defined schedules.
2. Kubernetes resource manifests are serialized and stored in the MinIO `velero` bucket.
3. The node agent (DaemonSet) handles file-system-level backup of PersistentVolume data using Kopia.
4. Both resource manifests and volume data are stored in MinIO, which persists to NFS.

!!! warning "Restore prerequisites"
    Recovery credentials must be available outside Vault. Offsite-only bootstrap does not require a working MinIO or ESO. KMS auto-unseal requires existing Vault data; it does not recreate it. Follow the staged [disaster recovery procedure](../runbooks/disaster-recovery.md#complete-cluster-rebuild), and do not start ordinary workloads until their data is restored.

Local-path/hostPath data is not captured by file-system backup. SQLite/native dumps and mounted holder pods bridge part of that gap; live NFS databases still require application-consistency and restore validation. See [Backup Architecture](../architecture/backups.md).

## Upstream Documentation

<https://velero.io>
