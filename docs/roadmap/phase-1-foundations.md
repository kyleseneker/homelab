# Phase 1 -- Foundations

**Status:** In progress

**Goal:** Protect against the failures that would cause unrecoverable data loss or hardware damage.

These are physical-layer changes. A power event or drive failure today could take out production data, backups, and the boot drive simultaneously.

**Addresses:** [P1, P2](assessment.md#physical-layer) (no UPS, single NAS drive), [K16](assessment.md#kubernetes--software-layer) (no etcd snapshot)

---

## 1.1 Add a UPS

- [ ] Select a pure sine wave UPS in the 1000-1500VA range (e.g., APC Smart-UPS, CyberPower PFC Sinewave)
- [ ] Install in the rack, powering the MS-01, UNAS Pro, USW-16-PoE, and PDU
- [ ] Configure NUT (Network UPS Tools) on Proxmox for graceful VM shutdown on low battery
- [ ] Add a `pve_ups` Ansible role to `pve-host.yml` for NUT configuration
- [ ] Add a PrometheusRule for UPS battery health (if NUT exporter is available)

| | |
|---|---|
| **Why** | A power flicker can corrupt NVMe writes, cause unclean etcd shutdown, or kill the NAS mid-IO. The PDU Pro monitors power but cannot protect against outages. |
| **Note** | Pure sine wave output matters. The MS-01 and NAS have active PFC power supplies that can malfunction on simulated sine wave units. |

## 1.2 Add NAS Drive Redundancy

- [ ] Purchase at least one additional WD80EFPX (or equivalent CMR drive)
- [ ] Configure a mirrored pool (RAID 1) on the UNAS Pro
- [ ] Verify NFS exports and Kubernetes PVCs still function after the pool migration
- [ ] Update [hardware inventory](../reference/hardware.md) with new drive configuration

| | |
|---|---|
| **Why** | A single drive failure loses all NFS-backed data: media, app configs, Prometheus, Loki, Vault, and Velero backups. |
| **Sizing** | The UNAS Pro supports 4 drives. Start with a 2-drive mirror. A 4-drive RAID 10 (Phase 4.4) adds capacity and read performance later. |
| **Note** | RAID is not backup. This protects against drive failure, not deletion, corruption, or ransomware. Offsite backup (1.3) addresses that. |

## ~~1.3 Add Offsite Backup Target~~ Done

Completed 2026-03-28. Velero writes weekly offsite backups to AWS S3 (`velero-offsite-homelab` in us-east-1). See [ADR-013](../decisions/013-velero-minio-backups.md) and the [backup runbook](../runbooks/backup-and-restore.md).

## 1.4 Add etcd Snapshot Schedule

- [ ] Create a CronJob (or systemd timer on the control plane) running `etcdctl snapshot save` on a schedule
- [ ] Store snapshots on the NAS via NFS (separate from the etcd data directory)
- [ ] Retain at least 7 daily snapshots
- [ ] Add a PrometheusRule for snapshot age (alert if latest snapshot is older than 36 hours)
- [ ] Document the restore procedure in the DR runbook

| | |
|---|---|
| **Why** | Velero backs up Kubernetes API resources, but an etcd corruption or unclean shutdown on the single control plane could leave the cluster unrecoverable without a raw etcd snapshot. This is especially urgent with only one CP node. |
| **Note** | This becomes less critical after Phase 4 adds a 3-node etcd quorum, but remains a good practice for point-in-time recovery. |

---

## Definition of Done

- [ ] UPS protecting all rack gear with automated graceful shutdown on low battery
- [ ] NAS running a mirrored drive pool
- [x] Velero writing weekly backups to an offsite object store
- [ ] Restore from offsite backup tested successfully (pending first weekly run)
- [ ] etcd snapshots running daily with alerting on staleness
