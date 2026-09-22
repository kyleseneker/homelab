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

Use the [isolated restore lab](../runbooks/restore-lab.md) for the remaining checks below. The runbooks retain the verified Sonarr offsite restore and controller-reconciliation procedures and results; this backlog tracks unfinished recovery work.

- [ ] Build a fresh Packer template, replace the lab cloud-image template, and repeat identity, prerequisite and reboot checks
- [ ] Bootstrap ArgoCD and its Applications without preexisting CRDs or Secrets; confirm dependencies converge
- [ ] Set acceptable data-loss and recovery-time targets for the [inventoried data](../architecture/backups.md#recovery-coverage); close the documented non-database and unprotected-volume gaps
- [ ] Compare daily local dumps and weekly offsite schedules with those targets; adjust the schedule where needed
- [ ] Restore etcd + matching PKI into an isolated replacement control plane using the [DR runbook](../runbooks/disaster-recovery.md)
- [ ] Recover production tracker definitions/credentials, download-client/notification connections and Vault/ESO bootstrap; validate the remaining Bazarr/Prowlarr profile IDs and verify production authentication
- [ ] Rebuild Gluetun/VPN access and verify download-payload recovery before resuming qBittorrent transfers
- [ ] Exercise the restored Tdarr flows on a copied media fixture, including library-specific replacement/deletion behavior
- [ ] Verify Authentik ordinary password/MFA login, client application login, proxy outposts and worker behavior after the verified emergency-login/OIDC restore
- [ ] Repeat S3 recovery using credentials available outside the production cluster, with MinIO and the original NAS unavailable; extend the verified Sonarr database procedure to the remaining required data
- [ ] Keep an independently protected bootstrap credential copy and account/MFA recovery outside the homelab and HCP; HCP-based KMS/S3 retrieval is verified
- [ ] Review backup credentials and S3 retention/deletion controls; versioning and Terraform deletion guards alone do not provide an immutable copy

## 1.3 Verify Backup and Power Alerts

- [ ] Test missing-backup and failed-upload alerts through to the external recipient
- [ ] Test the external Watchdog heartbeat by interrupting delivery in a controlled window
- [ ] Test UPS USB stability and orderly shutdown; record the result
- [ ] Rehearse recovery quarterly and after storage, backup-format, or major application upgrades

---

## Definition of Done

- [ ] NAS running a mirrored drive pool
- [ ] Independent etcd recovery and an application restore using externally held credentials demonstrated
- [ ] Offsite recovery demonstrated with the original NAS unavailable
- [ ] Backup alerts and UPS shutdown verified
