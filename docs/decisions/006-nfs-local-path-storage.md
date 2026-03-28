# ADR-006: NFS and Local-Path Storage

## Status

Accepted

## Context

The cluster needs persistent storage for application configuration, databases, media files, and backups. The storage solution must support dynamic provisioning and shared access for the media stack's hardlink-based workflow.

## Decision

Use two storage provisioners, each suited to its workload:

- **NFS Subdir External Provisioner** (`nfs-client` StorageClass): Default for shared media and most application config. Backed by the Unifi NAS with a Retain reclaim policy.
- **Rancher Local-Path Provisioner** (`local-path` StorageClass): Node-local storage for applications with SQLite databases that require proper POSIX file locking (Sonarr, Radarr). Uses `WaitForFirstConsumer` binding and a Retain reclaim policy. Data stored at `/opt/local-path-provisioner/` on worker nodes.

## Alternatives Considered

- **Longhorn**: Distributed block storage with replication. Provides HA at the storage layer but consumes significant CPU, memory, and disk on each node. On a single-host cluster (all VMs on one physical machine), replication provides no real durability benefit.
- **Rook-Ceph**: Enterprise-grade distributed storage. Even heavier than Longhorn. Designed for multi-node clusters with dedicated storage disks.
- **local-path-provisioner only**: Simple and fast but ties PVCs to specific nodes with no failover. Media files would need to be on every node or use a shared mount. Used selectively for SQLite workloads where NFS locking is insufficient.
- **Direct NFS PVs**: Manual PV/PVC creation per application without dynamic provisioning. Works but doesn't scale and requires manual intervention for each new app.

## Rationale

- **Pre-existing NAS**: The Unifi NAS already hosts the media library. Using it as the storage backend avoids duplicating data and leverages existing hardware.
- **Shared media volume**: The *arr stack requires all applications (Sonarr, Radarr, qBittorrent, Jellyfin, Tdarr) to access the same filesystem for hardlinks and atomic moves. NFS naturally supports this via a shared PVC (`arr-data`).
- **Dynamic provisioning**: The provisioner creates per-app subdirectories automatically using a `${namespace}-${pvcname}` path pattern.
- **Retain policy**: PVC data persists on the NAS even when the cluster is destroyed, enabling disaster recovery without restoring from backup.
- **Simplicity**: No distributed storage overhead. On a single physical host, NFS to an external NAS is the simplest reliable option.

## Consequences

- NFS latency spikes can cause probe failures. Application health check timeouts have been tuned to tolerate this (multiple commits adjusting probe tolerances).
- SQLite databases require proper POSIX file locking that NFS cannot provide. Applications with SQLite databases (Sonarr, Radarr) use `local-path` instead of `nfs-client` for their config volumes.
- Local-path volumes are tied to a specific worker node. If a pod reschedules to a different node, it cannot access the data. Velero backups cover disaster recovery for these volumes.
- Single NAS is a single point of failure for all persistent storage. A backup strategy for persistent data is essential to mitigate this risk.
