# Config Backup

Nightly SQLite dumps of every *arr application's configuration database onto an NFS volume that Velero can actually read.

## Details

| Property | Value |
|----------|-------|
| Type | CronJobs + holder Deployment (`sourceType: git`) |
| Namespace | `arr` |
| ArgoCD app | `arr-config-backup` |
| Image | `python:3.13-alpine` |
| Target PVC | `arr-config-backups` (`nfs-client`, 2Gi) |
| Schedules | Staggered, 01:30--01:36 daily |

## Why It Exists

Every *arr config PVC lives on `local-path`, which provisions `hostPath` volumes. Velero's Kopia file-system backup cannot read `hostPath`, so those PVCs are captured as objects containing **no data** -- and Velero records that as a warning, not an error, so the backup still reports `Completed`. A restore would recreate them empty.

Copying the raw SQLite file is not a fix either: a live WAL-mode database copied byte-for-byte is not guaranteed consistent. Each job instead uses SQLite's online backup API, which produces a consistent snapshot of a database that is being written to.

## What Gets Backed Up

| App | Schedule | Method |
|-----|----------|--------|
| Bazarr | `30 1 * * *` | SQLite online backup |
| Jellyfin | `31 1 * * *` | SQLite online backup |
| Prowlarr | `32 1 * * *` | SQLite online backup |
| Radarr | `33 1 * * *` | SQLite online backup |
| Seerr | `34 1 * * *` | SQLite online backup |
| Sonarr | `35 1 * * *` | SQLite online backup |
| Tdarr | `36 1 * * *` | Tdarr's own native archive |

Tdarr is the exception: it ships its own backup format, which is consistent by construction, so the job copies that rather than reaching into its database.

Uptime Kuma is covered separately by `uptime-kuma-backup`, which does the same for `kuma.db`.

## The Holder Deployment

`arr-config-backup-holder` is a `pause` container that exists only to keep the `arr-config-backups` PVC mounted.

!!! danger "Without the holder, this backs up nothing"
    Velero's file-system backup only reads volumes attached to a **running** pod. An unmounted PVC is captured as an object with no data -- exactly the failure this whole mechanism exists to avoid. The holder is not optional and must not be scaled to zero.

## Alerting

| Alert | Fires when |
|-------|-----------|
| `ArrConfigBackupStale` | No successful dump within the expected window |
| `ArrConfigBackupFailed` | A CronJob's last run failed |
| `ArrConfigBackupVolumeUnmounted` | The holder is absent, so the volume is invisible to Velero |

The third alert covers the failure mode that would otherwise be silent: everything reports healthy while nothing is actually being captured.

## Restoring

The dumps are plain SQLite files on the `arr-config-backups` volume. Restore by stopping the target application, copying the dump over its `/config` database, and starting it again.
