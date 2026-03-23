# Storage

This document covers the storage architecture, including the NFS dynamic provisioner, the shared media volume, per-application configuration volumes, and the NAS folder structure.

## Storage Architecture

```mermaid
flowchart TD
    subgraph nas["Unifi NAS"]
        nfsExport["/data NFS Export"]
        configExport["Config NFS Exports"]
    end

    subgraph k8sCluster["Kubernetes Cluster"]
        nfsProv["NFS Subdir External Provisioner"]
        scNfsClient["StorageClass: nfs-client"]

        subgraph sharedVol["Shared Media Volume"]
            arrPV["PV: arr-data (10Ti)"]
            arrPVC["PVC: arr-data"]
        end

        subgraph dynamicVols["Dynamic Config Volumes"]
            sonarrPVC["PVC: sonarr-config"]
            radarrPVC["PVC: radarr-config"]
            prowlarrPVC["PVC: prowlarr-config"]
            otherPVC["PVC: ..."]
        end

        subgraph appPods["Application Pods"]
            jellyfin["Jellyfin"]
            sonarr["Sonarr"]
            radarr["Radarr"]
            tdarr["Tdarr"]
            otherApps["..."]
        end
    end

    nfsExport --> arrPV
    configExport --> nfsProv
    nfsProv --> scNfsClient
    scNfsClient --> dynamicVols
    arrPVC --> appPods
    dynamicVols --> appPods
```

## NFS Subdir External Provisioner

The NFS Subdir External Provisioner dynamically creates PersistentVolumes backed by subdirectories on the Unifi NAS. It eliminates the need to manually pre-create PVs for each application.

### Configuration

| Setting | Value |
|---------|-------|
| StorageClass Name | `nfs-client` |
| NFS Server | Unifi NAS |
| Path Pattern | `${.PVC.namespace}-${.PVC.name}` |
| Reclaim Policy | Retain |
| Sync Wave | -2 |

The `pathPattern` creates predictable directory names on the NAS. For example, a PVC named `sonarr-config` in the `arr` namespace creates the NFS subdirectory `arr-sonarr-config`.

!!! info "Default StorageClass"
    `nfs-client` serves as the default StorageClass for the cluster. Any PVC that does not specify a `storageClassName` will be provisioned by this provisioner.

## Shared Media Volume (arr-data)

All media applications share a single 10Ti PersistentVolume backed by the `/data` export on the Unifi NAS. This shared volume enables applications to access media files without copying data between volumes.

### Volume Specification

| Property | Value |
|----------|-------|
| PV Name | `arr-data` |
| Capacity | 10Ti |
| Access Mode | ReadWriteMany |
| NFS Path | `/data` |
| NFS Server | Unifi NAS |
| PVC Name | `arr-data` |
| PVC Namespace | `arr` |

Each application mounts the shared PVC at `/data` within its pod, maintaining a consistent path structure that matches the NAS layout. This allows Sonarr, Radarr, and other apps to perform hardlinks and atomic moves instead of cross-device copies.

!!! tip "Hardlinks and Atomic Moves"
    Because all applications share the same underlying NFS mount, file operations like hardlinks and atomic moves work correctly. This is critical for the arr stack workflow where Sonarr/Radarr move completed downloads into the media library without duplicating data.

## NAS Folder Structure

The NAS follows the recommended media server folder structure, keeping downloads and library content under a single `/data` root:

```
/data/
  torrents/
    movies/
    tv/
    music/
    books/
  usenet/
    movies/
    tv/
    music/
    books/
  media/
    movies/
    tv/
    music/
    books/
```

### Path Mapping by Application

| Application | Mount Path | NAS Subdirectory Used |
|------------|-----------|----------------------|
| qBittorrent | `/data/torrents` | Torrent download destination |
| SABnzbd | `/data/usenet` | Usenet download destination |
| Sonarr | `/data` | Manages `/data/media/tv`, imports from `/data/{torrents,usenet}/tv` |
| Radarr | `/data` | Manages `/data/media/movies`, imports from `/data/{torrents,usenet}/movies` |
| Bazarr | `/data/media` | Reads media directories for subtitle matching |
| Jellyfin | `/data/media` | Serves content from media library |
| Tdarr | `/data/media` | Transcodes media files in-place |

## Per-Application Config Volumes

Each application also has its own dynamically provisioned PVC for configuration and database storage. These are created via the `nfs-client` StorageClass and hold application-specific data (databases, configuration files, logs).

| Application | PVC Name | Typical Size |
|------------|----------|-------------|
| Jellyfin | `jellyfin-config` | 10Gi - 50Gi |
| Sonarr | `sonarr-config` | 1Gi - 5Gi |
| Radarr | `radarr-config` | 1Gi - 5Gi |
| Prowlarr | `prowlarr-config` | 1Gi |
| Bazarr | `bazarr-config` | 1Gi |
| Jellyseerr | `jellyseerr-config` | 1Gi |
| Tdarr | `tdarr-config` | 1Gi |

## Infrastructure Storage

Several infrastructure components also use `nfs-client` for persistent storage:

| Component | PVC | Size | Purpose |
|-----------|-----|------|---------|
| Prometheus | `prometheus-data` | 20Gi | Metrics time-series data (15d retention) |
| Loki | `loki-data` | 10Gi | Log storage (168h retention) |
| Grafana | `grafana-data` | Persistent | Dashboards and data source configuration |
| MinIO | `minio-data` | 50Gi | S3 backup object storage |
