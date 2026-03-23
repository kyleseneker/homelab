# NFS Provisioner

The NFS Provisioner dynamically creates PersistentVolumes backed by an NFS share, providing the default storage class for the cluster.

## Details

| Field | Value |
|-------|-------|
| Chart | `nfs-subdir-external-provisioner` |
| Repository | <https://kubernetes-sigs.github.io/nfs-subdir-external-provisioner> |
| Version | 4.0.18 |
| Namespace | `nfs-provisioner` (CreateNamespace=true) |
| Sync Wave | -2 |

## Key Configuration

- **NFS Server**: `192.168.1.158` (Unifi NAS data export)
- **Mount Options**: `vers=3`, `hard`, `intr`
- **StorageClass**: `nfs-client`
    - Set as the cluster default storage class
    - Reclaim policy: `Retain` (volumes are preserved after PVC deletion)
    - Path pattern: `${.PVC.namespace}-${.PVC.name}` (directories on the NFS share are named predictably by namespace and PVC name)

## Cluster Integration

`nfs-client` is the default StorageClass, so any PVC without an explicit `storageClassName` is fulfilled by this provisioner. It is used extensively across the cluster:

- Application configuration volumes (Sonarr, Radarr, Jellyfin, etc.)
- Prometheus time-series data (20Gi)
- Grafana dashboards and plugin storage (2Gi)
- Loki log data (10Gi)
- MinIO object storage (50Gi)

The provisioner deploys at sync wave -2 so that storage is available before the monitoring stack, backup services, and applications request PVCs at wave -1 and wave 0.

## Upstream Documentation

<https://github.com/kubernetes-sigs/nfs-subdir-external-provisioner>
