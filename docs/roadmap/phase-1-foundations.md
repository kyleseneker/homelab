# Phase 1 -- Foundations

**Status:** In progress

**Goal:** Protect against the failures that would cause unrecoverable data loss or hardware damage.

UPS/NUT, Garage + offsite S3, etcd snapshots, and local SQLite-to-NFS backup bridges are implemented. NAS drive redundancy, the UPS network card, recovery drills and automated restore tests remain open.

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

Use the [isolated restore lab](../runbooks/restore-lab.md) for the remaining checks below. The runbooks retain the verified machine/network, offsite application-restore and controller-reconciliation procedures and results; this backlog tracks unfinished recovery work.

- [ ] Set acceptable data-loss and recovery-time targets for the [inventoried data](../architecture/backups.md#recovery-coverage); close the documented non-database and unprotected-volume gaps
- [ ] Compare daily local dumps and weekly offsite schedules with those targets; adjust the schedule where needed
- [ ] Recover production tracker definitions/credentials, download-client/notification connections and Vault/ESO bootstrap; validate the remaining Bazarr/Prowlarr profile IDs and verify production authentication
- [ ] Rebuild Gluetun/VPN access and verify download-payload recovery before resuming qBittorrent transfers
- [ ] Exercise the restored Tdarr flows on a copied media fixture, including library-specific replacement/deletion behavior
- [ ] Verify Authentik ordinary password/MFA login, client application login, proxy outposts and worker behavior after the verified emergency-login/OIDC restore
- [ ] Extend the verified [independent and combined S3 recovery](../runbooks/restore-lab.md#combined-machine-and-application-recovery-drill) to remaining required application data, keeping production, local object store and NAS data access unavailable
- [ ] Keep an independently protected bootstrap credential copy and account/MFA recovery outside the homelab and HCP; HCP-based KMS/S3 retrieval is verified
- [ ] Review backup credentials and S3 retention/deletion controls; versioning and Terraform deletion guards alone do not provide an immutable copy

## 1.3 Verify Backup and Power Alerts

- [ ] Test missing-backup and failed-upload alerts through to the external recipient
- [ ] Test the external Watchdog heartbeat by interrupting delivery in a controlled window
- [ ] Test UPS monitoring stability and orderly shutdown; record the result
- [ ] Rebuild the [restore lab](../runbooks/restore-lab.md) from production's cluster definition, with an overlay for addresses, credentials, storage and VM sizing, and retire the lab's own application definitions
- [ ] Rehearse recovery quarterly and after storage, backup-format, or major application upgrades on the rebuilt lab: recover from S3 alone, run the [ADR-034](../decisions/034-restore-testing.md) checks against it and restore one application in place by the runbook

## 1.4 Automate Restore Tests

Finish the [restore test](../infrastructure/restore-test.md) for every [ADR-034](../decisions/034-restore-testing.md) target. Every Velero-held dump already restores nightly with the integrity and freshness tiers.

- [ ] Trigger `RestoreTestStale`, `RestoreTestMissing`, `RestoreTestRowsDropped`, `RestoreSandboxLingering` and `RestoreTestVolumesOrphaned` once on purpose and confirm each reaches Slack
- [ ] Add the application tiers for Bazarr, Jellyfin, Seerr, Tdarr and Uptime Kuma, listing known backup gaps in the expected-failure register
- [ ] Decrypt Home Assistant's newest archive with its key from Vault and list its contents
- [ ] Add the weekly S3 run
- [ ] Add the monthly Vault restore with a canary-only token
- [ ] Replace "application restore unverified" in the [recovery coverage](../architecture/backups.md#recovery-coverage) with each target's verified tiers

## 1.5 Add a UPS Network Card

- [ ] Purchase a CyberPower RMCARD205, the card the CP1500PFCRM2U datasheet lists for its expansion slot
- [ ] Connect it on the Management VLAN with SNMPv3 only, disable HTTP, Telnet and FTP, and update its firmware
- [ ] Check whether the UPS's USB port still works with the card installed
- [ ] Move the `pve_ups` role from `usbhid-ups` to `snmp-ups` and back to Debian's NUT packages, in an ADR that supersedes [ADR-031](../decisions/031-nut-backport.md)
- [ ] Send the card's own power alerts by email or syslog
- [ ] Optionally add an SNEV001 sensor at the top front of the rack for closet temperature, humidity and a door contact
- [ ] Update the [hardware inventory](../reference/hardware.md), the [NUT exporter](../infrastructure/nut-exporter.md) page and the [network infrastructure](../architecture/network-infrastructure.md) docs

| | |
|---|---|
| **Why** | The UPS fails about 25 USB report reads a minute, which only the NUT backport tolerates. Over SNMP, NUT runs on Debian's packages, and the card can raise power alerts while the Proxmox host or the cluster is down. |
| **Note** | Prometheus runs on the same host, so UPS metrics still stop during a host outage; the card's own alerts cover that gap. The UPS has no switchable outlet banks, and the USP PDU Pro already switches outlets. |

---

## Definition of Done

- [ ] NAS running a mirrored drive pool
- [ ] Independent etcd recovery and an application restore using externally held credentials demonstrated
- [ ] Offsite recovery demonstrated with the original NAS unavailable
- [ ] Backup alerts and UPS shutdown verified
- [ ] Automated restore tests pass nightly from the local copy and weekly from S3 for every [ADR-034](../decisions/034-restore-testing.md) target, apart from listed known gaps
