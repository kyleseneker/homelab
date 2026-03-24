# MinIO

MinIO provides S3-compatible object storage within the cluster, serving as the backup target for Velero.

## Details

| Field | Value |
|-------|-------|
| Chart | `minio` |
| Repository | <https://charts.min.io> |
| Version | 5.4.0 |
| Namespace | `backups` (CreateNamespace=true) |
| Sync Wave | -2 |

## Key Configuration

- **Mode**: `standalone` (single-node, single-drive)
- **Credentials**: Sourced from the ExternalSecret `minio-credentials` (synced from Vault, keys: `rootUser`, `rootPassword`)
- **Storage**: 50Gi PVC using the `nfs-client` StorageClass
- **Pre-created buckets**:
    - `velero` (policy: `none`, purge: `false`)
- **Console ingress**: Disabled
- **Resources**:
    - Requests: 100m CPU, 256Mi memory
    - Limits: 512Mi memory

## Cluster Integration

MinIO deploys at sync wave -2 so it is available before Velero (wave -1) starts. Velero connects to MinIO as its S3-compatible backup storage location at:

```
http://minio.backups.svc.cluster.local:9000
```

The `velero` bucket is automatically created during MinIO startup via the `buckets` Helm value, ensuring the backup target exists before Velero begins scheduling backups.

!!! info "Why MinIO?"
    Running an in-cluster S3-compatible store avoids dependency on external cloud storage for backups while keeping the Velero configuration standard. The backup data itself is stored on the NFS share via the `nfs-client` PVC, providing a layer of separation from the cluster's ephemeral storage.

## Upstream Documentation

<https://min.io>
