# Phase 1 -- Foundations

**Status:** In progress

**Goal:** Protect against the failures that would cause unrecoverable data loss or hardware damage.

UPS/NUT, MinIO + offsite S3, etcd snapshots, and local SQLite-to-NFS backup bridges are implemented. NAS drive redundancy and recovery drills remain open.

**Addresses:** P1, P2, P7, K5, K16, K33, and K41 in the [assessment](assessment.md).

---

## 1.1 Add NAS Drive Redundancy

- [ ] Purchase at least one additional WD80EFPX (or equivalent 8 TB CMR drive)
- [ ] Confirm the UNAS model/firmware's supported migration from the current single-drive pool to a two-drive mirror
- [ ] Take and verify an independent backup before changing the pool
- [ ] Configure a mirrored pool (RAID 1) on the UNAS
- [ ] Verify NFS exports and Kubernetes PVCs still function after the pool migration
- [ ] Update [hardware inventory](../reference/hardware.md) with the new drive configuration

| | |
|---|---|
| **Why** | A single NAS drive failure loses the active NFS data and the backups stored on that same drive. Local application state is separate, but its NFS backup copies share this failure domain. |
| **Sizing** | Start with a two-drive, 8 TB usable mirror. The four-drive expansion in [Phase 4.4](phase-4-compute-and-storage.md#44-expand-nas-storage) targets 16 TB usable capacity. |
| **Note** | RAID protects against drive failure. Offsite backups and etcd snapshots provide recovery from deletion, corruption, or site loss; see [ADR-013](../decisions/013-backup-strategy.md). |

## 1.2 Verify Recovery

Start with one disposable control plane and worker, using separate credentials, a separate kubeconfig and writable paths that cannot touch production data. Build and bootstrap them from this repository, then restore one application from S3. This first complete recovery provides the procedure and timing baseline for the remaining services.

- [ ] Build a fresh Packer clone and isolated cluster; verify unique machine/SSH identity, Cilium startup and a worker join
- [ ] Bootstrap ArgoCD and its Applications without preexisting CRDs or Secrets; confirm dependencies converge
- [ ] Inventory every PVC and application: recoverable data, backup mechanism, exclusions, destination and acceptable data loss/recovery time
- [ ] Inspect Velero backup warnings, volume exclusions and PodVolumeBackup results; confirm each required data volume was actually captured
- [ ] Compare daily local dumps and weekly offsite schedules with those targets; adjust the schedule where needed
- [ ] Restore etcd + matching PKI into an isolated replacement control plane using the [DR runbook](../runbooks/disaster-recovery.md)
- [ ] Restore Vault data and test KMS auto-unseal, Kubernetes auth, and ESO with credentials available outside the cluster
- [ ] Restore one SQLite application from its application-consistent dump, including non-database configuration; verify login and representative media state
- [ ] Test Tdarr archive recovery, Authentik database consistency, and qBittorrent resume/config coverage
- [ ] Restore from S3 with MinIO and the original NAS unavailable; record backup age, recovery time, and the data restored
- [ ] Keep bootstrap credentials and recovery instructions available outside the cluster and Vault
- [ ] Review backup credentials and S3 retention/deletion controls; versioning and Terraform deletion guards alone do not provide an immutable copy

## 1.3 Verify Backup and Power Alerts

- [ ] Test missing-backup and failed-upload alerts through to the external recipient
- [ ] Test the external Watchdog heartbeat by interrupting delivery in a controlled window
- [ ] Test UPS USB stability and orderly shutdown; record the result
- [ ] Rehearse recovery quarterly and after storage, backup-format, or major application upgrades

---

## Definition of Done

- [ ] NAS running a mirrored drive pool
- [ ] Independent restores of etcd, Vault, and an application demonstrated
- [ ] Offsite recovery demonstrated with the original NAS unavailable
- [ ] Backup alerts and UPS shutdown verified
