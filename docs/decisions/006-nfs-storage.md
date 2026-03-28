# ADR-006: NFS External Provisioner for Storage

## Status

Accepted

## Context

The cluster needs persistent storage for application configuration, databases, media files, and backups. The storage solution must support dynamic provisioning and shared access for the media stack's hardlink-based workflow.

## Decision

Use the NFS Subdir External Provisioner with a Unifi NAS as the backing store. All PVCs use the `nfs-client` StorageClass with a Retain reclaim policy.

## Alternatives Considered

- **Longhorn**: Distributed block storage with replication. Provides HA at the storage layer but consumes significant CPU, memory, and disk on each node. On a single-host cluster (all VMs on one physical machine), replication provides no real durability benefit.
- **Rook-Ceph**: Enterprise-grade distributed storage. Even heavier than Longhorn. Designed for multi-node clusters with dedicated storage disks.
- **local-path-provisioner**: Simple and fast but ties PVCs to specific nodes with no failover. Media files would need to be on every node or use a shared mount.
- **Direct NFS PVs**: Manual PV/PVC creation per application without dynamic provisioning. Works but doesn't scale and requires manual intervention for each new app.

## Rationale

- **Pre-existing NAS**: The Unifi NAS already hosts the media library. Using it as the storage backend avoids duplicating data and leverages existing hardware.
- **Shared media volume**: The *arr stack requires all applications (Sonarr, Radarr, qBittorrent, Jellyfin, Tdarr) to access the same filesystem for hardlinks and atomic moves. NFS naturally supports this via a shared PVC (`arr-data`).
- **Dynamic provisioning**: The provisioner creates per-app subdirectories automatically using a `${namespace}-${pvcname}` path pattern.
- **Retain policy**: PVC data persists on the NAS even when the cluster is destroyed, enabling disaster recovery without restoring from backup.
- **Simplicity**: No distributed storage overhead. On a single physical host, NFS to an external NAS is the simplest reliable option.

## Consequences

- NFS latency spikes can cause probe failures. Application health check timeouts have been tuned to tolerate this (multiple commits adjusting probe tolerances).
- SQLite databases on NFS can experience locking issues under load. The *arr apps handle this internally but it's a known NFS limitation.
- Single NAS is a single point of failure for all persistent storage. A backup strategy for persistent data is essential to mitigate this risk.
