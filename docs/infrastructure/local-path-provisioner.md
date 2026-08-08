# Local-Path Provisioner

The Rancher Local-Path Provisioner creates node-local PersistentVolumes backed by a directory on the node's disk. It exists to host SQLite databases, which cannot run correctly over NFS.

## Details

| Field | Value |
|-------|-------|
| Type | Plain manifests (`sourceType: kustomize`) |
| Namespace | `local-path-storage` |
| StorageClass | `local-path` |
| Volume binding mode | `WaitForFirstConsumer` |
| Reclaim policy | `Retain` |
| Node path | `/opt/local-path-provisioner` |
| Helper image | `busybox` |

## Why Not NFS

Every *arr application stores its configuration in SQLite running in WAL mode. WAL coordinates readers and writers through a memory-mapped `-shm` file, and memory-mapped shared coordination is not something a network filesystem provides. This is a distinct problem from byte-range locking -- NFSv4 does implement locking, but that is not the mechanism WAL uses.

The result on NFS was database lock contention and corruption risk. These workloads were moved to `local-path` deliberately.

The Prometheus TSDB is on `local-path` for a different reason: heavy random I/O over NFS degrades query performance and risks TSDB corruption.

## Consequences

**Pods are pinned to a node.** `WaitForFirstConsumer` binds the volume where the pod first schedules. That pod cannot move afterwards. If the node is lost, the workload cannot start until the node returns.

**Volumes are not backed up.** Velero's Kopia file-system backup cannot read `hostPath` volumes. Every `local-path` PVC is captured as a PVC and PV object holding no data, and Velero logs this as a *warning* -- the backup still reports `Completed`.

!!! danger "A restore recreates these volumes empty"
    Coverage is provided at the application layer instead. `arr-config-backup` dumps each *arr SQLite database nightly through SQLite's online backup API onto an `nfs-client` volume Velero does read; `uptime-kuma-backup` does the same for `kuma.db`. The Prometheus TSDB is deliberately left uncovered.

    Both backup jobs depend on a holder Deployment keeping the target volume mounted -- fs-backup only reads volumes attached to a running pod, so without the holder the mechanism silently captures nothing.

## Consumers

All *arr config PVCs (Jellyfin, Sonarr, Radarr, Prowlarr, Bazarr, Seerr, Tdarr), the Uptime Kuma database, and the Prometheus TSDB. See [Storage](../architecture/storage.md#per-application-config-volumes) for sizes.

## Upstream Documentation

<https://github.com/rancher/local-path-provisioner>
