# Phase 1 -- Foundations

**Status:** In progress

**Goal:** Protect against the failures that would cause unrecoverable data loss or hardware damage.

These are physical-layer changes. A power event or drive failure today could take out production data, backups, and the boot drive simultaneously.

**Addresses:** [P1, P2](assessment.md#physical-layer) (no UPS, single NAS drive)

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
| **Note** | RAID is not backup. This protects against drive failure, not deletion, corruption, or ransomware. Offsite backups and etcd snapshots address that (see [ADR-013](../decisions/013-backup-strategy.md)). |

---

## Definition of Done

- [ ] UPS protecting all rack gear with automated graceful shutdown on low battery
- [ ] NAS running a mirrored drive pool
