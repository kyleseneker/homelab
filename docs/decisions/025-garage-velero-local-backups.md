# ADR-025: Garage for Local Velero Backups

## Status

Accepted

## Context

[ADR-013](013-backup-strategy.md) made standalone MinIO on an NFS-backed PVC the
local S3-compatible target for Velero. It holds the daily stateful backups (7-day
retention) and the weekly full-cluster backups (30-day retention). The weekly offsite
backup uses a separate S3 location. Nothing else in the cluster uses MinIO.

MinIO's community repository now states that it is no longer maintained and that the
community edition is distributed as source code only, without pre-compiled releases
([README](https://github.com/minio/minio#readme)). The pinned `quay.io/minio/minio`
and `quay.io/minio/mc` tags can no longer be pulled from quay.io or Docker Hub. When
the Kubernetes 1.32 upgrade drained its node on 2026-10-25, the rescheduled MinIO Pod
could not pull its image; MinIO now runs only where that image is still cached.

## Decision

Replace MinIO with [Garage](https://garagehq.deuxfleurs.fr/), an actively maintained
AGPL-3.0 S3-compatible object store with official `dxflrs/garage` images (v2.5.0
when decided). Garage implements the operations Velero and Kopia rely on, including
path-style requests, ListObjectsV2, DeleteObjects and multipart uploads
([S3 compatibility](https://garagehq.deuxfleurs.fr/documentation/reference-manual/s3-compatibility/)).

Run one Garage node with the repository's app-template chart (ADR-008) and a pinned
official image:

- Store metadata with the SQLite engine on `local-path` storage. Garage does not
  checksum its metadata; its documentation reports LMDB corruption after unclean
  shutdowns and recommends SQLite as the more robust engine
  ([deployment guidance](https://garagehq.deuxfleurs.fr/documentation/cookbook/real-world/)).
  Keeping the embedded database off NFS also avoids network-filesystem locking.
- Write automatic metadata snapshots (`metadata_auto_snapshot_interval`) to a
  separate `nfs-client` volume (`metadata_snapshots_dir`), so losing the node does
  not lose the object index.
- Store object data on `nfs-client` storage, as MinIO did. Garage checksums data
  blocks itself.
- Use `replication_factor = 1`.

Add Garage as a new Velero location with path-style access and make it the target of
the daily and weekly local schedules. Bucket credentials come from Vault through
External Secrets (ADR-007). Before switching, a test backup and restore through
Garage must succeed. The AWS plugin sends `CRC32` request checksums by default; if
Garage rejects them, set `checksumAlgorithm` to empty for this location only.

Keep the MinIO location read-only for restores until its retained local backups
expire (30 days), then remove MinIO. Do not repoint the existing location: Velero
removes its records of backups that are no longer present in the location's storage.
The offsite location and retention periods are unchanged.

## Alternatives Considered

- **Keep MinIO, built from source**: Preserves current behavior, but makes this
  repository responsible for building and patching images of a project whose
  maintainers have stopped community releases.
- **SeaweedFS**: Apache-2.0 with an official Helm chart and S3 gateway, but runs
  master, volume and filer services to serve one backup bucket.
- **Offsite S3 only**: Removes the local target, but every restore would download
  from AWS and depend on internet access, abandoning ADR-013's local-plus-offsite
  strategy.

## Consequences

- Garage's documentation reserves a replication factor of 1 for test deployments.
  The local copy has no redundancy, as with standalone MinIO before it; the offsite
  S3 location remains the durable copy.
- Garage does not implement bucket versioning or object lock, so the local target
  provides no immutability.
- The metadata volume pins Garage to one node, and local backups are unavailable
  while that node is drained. Recovering on another node requires restoring the
  latest metadata snapshot alongside the NFS data.
- Garage documents restic, Borg and Duplicity but not Velero or Kopia. The cutover
  backup and restore test is the compatibility evidence.
- Garage's own Helm chart lives in its source repository rather than a chart
  repository. Deploying with app-template avoids that dependency but makes this
  repository own Garage's configuration file.
- Existing local backups are not migrated. Restore points created before the
  cutover remain available only while MinIO still runs.
- Alerts, recovery helpers and documentation that name MinIO change with the
  cutover.
