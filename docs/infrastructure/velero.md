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

### S3 Backend (Garage)

- **Plugin**: `velero/velero-plugin-for-aws:v1.14.2` (provides S3 compatibility)
- **Location**: `local` (default)
- **Endpoint**: `http://garage.backups.svc.cluster.local:3900`
- **Bucket**: `velero`
- **Region**: `garage`
- **s3ForcePathStyle**: `true`
- **Credentials**: Sourced from the ExternalSecret `velero-local-credentials`, rendered from Vault `infrastructure/garage`

The legacy MinIO location `default` (`http://minio.backups.svc.cluster.local:9000`, credentials `velero-cloud-credentials`) is read-only. It keeps pre-cutover restore points available until they expire around 2026-11-24 ([ADR-025](../decisions/025-garage-velero-local-backups.md)).

### Volume Backup

- **Default method**: File system backup via Kopia (`defaultVolumesToFsBackup: true`)
- **Node agent**: Deployed as a DaemonSet on every node to handle file-system-level volume snapshots

### Backup Schedules

| Schedule | Cron | Scope | TTL |
|----------|------|-------|-----|
| `daily-stateful` | 03:00 UTC daily | `arr`, `monitoring`, `auth`, `openclaw` namespaces to `local` | 7 days |
| `weekly-full-cluster` | 04:00 UTC Sunday | All except `kube-system`, `kube-public`, `nfs-provisioner`, `backups`, to `local` | 30 days |
| `weekly-offsite` | 05:00 UTC Sunday | `arr`, `monitoring`, `auth`, `openclaw`, `argocd`, `vault`, `external-secrets` to `offsite` | 30 days |

### Resources

| Component | CPU Request | Memory Request | Memory Limit |
|-----------|-------------|----------------|--------------|
| Server | 100m | 128Mi | 512Mi |
| Node Agent | 100m | 128Mi | 1Gi |

## Cluster Integration

Velero depends on Garage for its default backup storage location. The backup workflow is:

1. Velero server creates a backup according to the defined schedules.
2. Kubernetes resource manifests are serialized and stored in the Garage `velero` bucket.
3. The node agent (DaemonSet) handles file-system-level backup of PersistentVolume data using Kopia.
4. Both resource manifests and volume data are stored in Garage, which persists object data to NFS.

!!! warning "Restore prerequisites"
    Recovery credentials must be available outside Vault. Offsite-only bootstrap does not require a working Garage, MinIO or ESO. KMS auto-unseal requires existing Vault data; it does not recreate it. Follow the staged [disaster recovery procedure](../runbooks/disaster-recovery.md#complete-cluster-rebuild), and do not start ordinary workloads until their data is restored.

Local-path/hostPath data is not captured by file-system backup. SQLite/native dumps and mounted holder pods bridge part of that gap; live NFS databases still require application-consistency and restore validation. See [Backup Architecture](../architecture/backups.md).

## Upstream Documentation

<https://velero.io>
