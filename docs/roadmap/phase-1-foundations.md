# Phase 1 -- Foundations

**Status:** In progress

**Goal:** Protect against the failures that would cause unrecoverable data loss or hardware damage.

These are physical-layer changes. A power event or drive failure today could take out production data, backups, and the boot drive simultaneously.

**Addresses:** [P2](assessment.md#physical-layer) (single NAS drive)

---

## 1.1 Add NAS Drive Redundancy

- [ ] Purchase at least one additional WD80EFPX (or equivalent CMR drive)
- [ ] Configure a mirrored pool (RAID 1) on the UNAS Pro
- [ ] Verify NFS exports and Kubernetes PVCs still function after the pool migration
- [ ] Update [hardware inventory](../reference/hardware.md) with new drive configuration

| | |
|---|---|
| **Why** | A single drive failure loses all NFS-backed data: media, app configs, Prometheus, Loki, Vault, and Velero backups. |
| **Sizing** | The UNAS Pro supports 4 drives. Start with a 2-drive mirror. A 4-drive RAID 10 (Phase 4.4) adds capacity and read performance later. |
| **Note** | RAID is not backup. This protects against drive failure, not deletion, corruption, or ransomware. Offsite backups and etcd snapshots address that (see [ADR-013](../decisions/013-backup-strategy.md)). |

---

## Definition of Done

- [ ] NAS running a mirrored drive pool
