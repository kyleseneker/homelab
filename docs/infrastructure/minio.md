# MinIO

MinIO provides S3-compatible object storage within the cluster, serving as the backup target for Velero.

## Details

| Field | Value |
|-------|-------|
| Chart | `minio` |
| Repository | <https://charts.min.io> |
| Version | 5.4.0 |
| Namespace | `backups` (CreateNamespace=true) |

## Key Configuration

- **Mode**: `standalone` (single-node, single-drive)
- **Credentials**: Sourced from the ExternalSecret `minio-credentials` (synced from Vault, keys: `rootUser`, `rootPassword`)
- **Storage**: 50Gi PVC using the `nfs-client` StorageClass
- **Bucket bootstrap**: `create-velero-bucket` Job creates `velero` without replacing it
- **Console ingress**: Disabled
- **Resources**:
    - Requests: 100m CPU, 256Mi memory
    - Limits: 512Mi memory

## Cluster Integration

Velero connects to MinIO as its S3-compatible backup storage location at:

```
http://minio.backups.svc.cluster.local:9000
```

The idempotent `create-velero-bucket` Job runs as an Argo CD `PostSync` hook after MinIO is healthy. Argo CD replaces the previous Job before each run and removes successful Jobs; failed Jobs remain available for inspection. This allows changes to the immutable Job template without a manual deletion. Inspect the Application's sync result and BackupStorageLocation status; Helm values do not configure bucket creation.

!!! info "Why MinIO?"
    Running an in-cluster S3-compatible store avoids dependency on external cloud storage for backups while keeping the Velero configuration standard. The backup data itself is stored on the NFS share via the `nfs-client` PVC, providing a layer of separation from the cluster's ephemeral storage.

## Upstream Documentation

<https://min.io>

MinIO shares the NAS failure domain with application storage. Retained NFS directories need explicit rebinding after a cluster rebuild. The offsite schedule excludes `backups` so MinIO archives are not copied into S3 a second time.
