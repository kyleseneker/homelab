# Garage

Garage provides S3-compatible object storage within the cluster, serving as Velero's local backup target. It replaced [MinIO](minio.md) ([ADR-025](../decisions/025-garage-velero-local-backups.md)).

## Details

| Field | Value |
|-------|-------|
| Chart | `app-template` |
| Repository | <https://bjw-s-labs.github.io/helm-charts> |
| Version | 5.3.0 |
| Image | `dxflrs/garage:v2.5.0` |
| Namespace | `backups` |

## Key Configuration

- **Mode**: Single node, `replication_factor = 1`
- **Metadata**: SQLite (`db_engine = "sqlite"`) on the 1Gi `local-path` PVC `garage-meta`
- **Metadata snapshots**: Every 6 hours to the 1Gi `nfs-client` PVC `garage-snapshots`
- **Data**: 50Gi PVC `garage-data` using the `nfs-client` StorageClass
- **Secrets**: ExternalSecret `garage-secrets` from Vault `infrastructure/garage` (keys: `rpcSecret`, `adminToken`, `accessKeyId`, `secretAccessKey`)
- **S3 region**: `garage`
- **Ports**: S3 API `3900`, admin API and `/metrics` `3903`
- **Resources**:
    - Requests: 50m CPU, 128Mi memory
    - Limits: 500m CPU, 512Mi memory

## Cluster Integration

Velero connects to Garage as its default `local` backup storage location at:

```
http://garage.backups.svc.cluster.local:3900
```

The idempotent `garage-setup` Job runs as an Argo CD `PostSync` hook. Through the admin API it assigns the node's layout, creates the `velero` bucket, imports the Velero key from Vault and grants it read/write access. It then puts, reads and deletes a probe object over S3, using the same CRC32 request checksums as Velero's AWS plugin. Argo CD removes successful Jobs; failed Jobs remain available for inspection.

Readiness and liveness probes check the S3 and admin listeners. `/health` returns `503` until a layout is applied, so probing it would block the first sync. The `GarageDown` alert fires when the Deployment has no available replica for 5 minutes, and a ServiceMonitor scrapes Garage's metrics.

!!! info "Why Garage?"
    MinIO's community edition is no longer distributed as images. Garage is actively maintained, publishes official images and implements the S3 operations Velero and Kopia use. Object data stays on the NAS like MinIO's did; only the metadata database is local, because an embedded database should not sit on NFS. It uses SQLite, which Garage recommends over LMDB for robustness after unclean shutdowns. A Velero backup and restore through Garage was verified before cutover.

## Upstream Documentation

<https://garagehq.deuxfleurs.fr/documentation/>

Garage shares the NAS failure domain with application storage, and its metadata volume pins it to one node. If that node is lost, restore the latest metadata snapshot from `garage-snapshots` alongside `garage-data`. Garage provides no bucket versioning or object lock. The offsite schedule excludes `backups`, so Garage archives are not copied into S3 a second time.
