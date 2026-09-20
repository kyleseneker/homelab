# Config Backup

Nightly SQLite dumps for six applications and a native Tdarr archive are staged onto NFS for Velero. These are database backups, not copies of every application file.

## Details

| Property | Value |
|----------|-------|
| Type | CronJobs + holder Deployment (`sourceType: git`) |
| Namespace | `arr` |
| ArgoCD app | `arr-config-backup` |
| Image | `python:3.14-alpine` |
| Target PVC | `arr-config-backups` (`nfs-client`, 2Gi) |
| Schedules | Staggered, 01:30--01:36 UTC daily |

## Why It Exists

The seven database-backed media application config PVCs live on `local-path`, which provisions `hostPath` volumes. Velero's Kopia file-system backup cannot read `hostPath`, so those PVCs are captured as objects containing **no data** -- and Velero records that as a warning, not an error, so the backup still reports `Completed`. A restore would recreate them empty.

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

Tdarr uses its native ZIP archive. The copy job verifies ZIP integrity and rejects an archive older than 48 hours so a stale source cannot report a successful fresh backup. Native backup scheduling must therefore produce an archive at least daily; confirm its restore behavior in a drill.

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

The dumps are plain SQLite files on the `arr-config-backups` volume. Follow [Backup & Restore](../runbooks/backup-and-restore.md#restoring-local-path-application-databases), including stopping writers, preserving/removing old WAL sidecars, restoring ownership, and validating data. Settings XML/JSON, plugins, artwork, and other non-database files are not captured by the SQLite dump. qBittorrent config uses NFS and follows the ordinary Velero path.
