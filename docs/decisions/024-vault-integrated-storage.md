# ADR-024: Vault Integrated Storage and Native Snapshots

## Status

Proposed

## Context

Production Vault uses a standalone file backend on NFS. Its live Velero copy is
not a consistent recovery point. A quiesced file copy has been restored locally
and from S3, but scheduling that procedure would interrupt Vault for every backup
and require a backup controller to stop/restart Vault and pause GitOps.

The restore lab has verified offline migration to integrated Raft storage,
KMS auto-unseal, existing authentication/ESO behavior, a native snapshot made by
a read-only backup identity, and restoration into fresh Raft storage. Production
has not been migrated.

## Decision

Propose using Vault integrated Raft storage on local persistent storage, initially
with one voter. Use native online snapshots instead of scheduled file-backend
shutdown/copy operations. Keep AWS KMS auto-unseal and Kubernetes authentication.

Propose a daily snapshot job that uses a short-lived Kubernetes-authenticated
Vault token with read permission only on `sys/storage/raft/snapshot`. The job
uploads to the existing S3 backup bucket, downloads the object again, and succeeds
only when the version and SHA-256 match. It needs no Kubernetes administration or
Vault root token. A 30-hour freshness alert detects missing successful backups.

Use a separate `vault-raft-snapshots/` prefix with 30-day current-object expiration;
the bucket's existing noncurrent-version expiration still applies. This is a
proposed default retention period, not an agreed recovery-point objective or
immutability guarantee. Existing manual file archives are unaffected.

## Alternatives Considered

- **Scheduled file-backend shutdown/copy**: Reuses the verified recovery path, but
  makes every backup a service interruption and grants the backup process control
  over Vault availability and GitOps reconciliation.
- **Continue live file copies**: Avoids interruptions but does not provide a proven
  consistent recovery point.
- **Wait for a three-voter deployment**: Defers online snapshots unnecessarily.
  Replication and host failure tolerance remain separate capacity/placement work.

## Consequences

- Production cutover requires an offline data migration and a controlled
  StatefulSet replacement. Changing a Helm storage setting alone is insufficient.
- The old NFS file data and verified offsite archive must be retained. Rollback to
  the old data is valid only before accepting new writes on Raft; it does not
  contain later writes.
- One local Raft voter is not highly available. Losing its node/storage requires
  recovery from a snapshot; increasing replica count alone is not a valid HA
  rollout. Every future voter needs its own storage, discovery and placement.
- Snapshot capture does not require stopping Vault or mounting its data volume.
  Direct offsite upload does not require the NAS or MinIO, but depends on AWS
  connectivity and a working existing offsite credential.
- Production activation, recurring upload verification and retention deployment
  remain pending. The lab snapshot CronJob is suspended and exercised manually.
