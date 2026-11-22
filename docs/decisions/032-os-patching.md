# ADR-032: Operating System Patching

## Status

Accepted

## Context

Renovate keeps the versions pinned in Git current: container images, Helm charts and the ArgoCD install manifest ([Renovate](../infrastructure/renovate.md)). Packages installed on the machines themselves are not in Git, so nothing tracked them.

- **Kubernetes nodes** (Ubuntu 24.04 VMs) ran `unattended-upgrades` with Ubuntu's defaults, so security updates installed daily. Nothing rebooted them, so kernel and library fixes waited for an unrelated host reboot.
- **The Proxmox host** had no automatic updates and no schedule. The `pve_repos` role could run a full upgrade (`pve_repos_upgrade_packages=true`), but only when someone remembered to. On 2026-11-21 the host was 242 packages behind, including 49 security updates and the Proxmox VE 9.1 to 9.2 upgrade, with no full upgrade for over three months. No alert reported it.

Common references set the bar this ADR adopts:

- **CIS Controls v8, Safeguards 7.3 and 7.4:** automated operating system and application patching, monthly or more often.
- **PCI DSS 4.0, Requirement 6.3.3:** critical and high-severity patches within one month of release.
- **CISA BOD 22-01:** known exploited vulnerabilities fixed within two weeks.
- **NIST SP 800-40 Rev. 4:** patching as routine maintenance with a regular cadence, an emergency path and tracking.

## Decision

**Targets:** security updates within 14 days of release; every other update within about one month.

### Proxmox Host

1. **Daily security updates.** The `pve_unattended_upgrades` role installs `unattended-upgrades`, limited to Debian's security repository (`origin=Debian,codename=trixie-security,label=Debian-Security`). Proxmox packages, regular Debian updates and the NUT backport repository ([ADR-031](031-nut-backport.md)) wait for the patch window. It never reboots the host.
2. **Monthly patch window.** The `pve_patch_window` role installs a systemd timer for the first Sunday of each month at 03:30 America/Chicago:
    - It runs `apt-get full-upgrade` with existing configuration files kept.
    - It reboots only if a package changed. The VMs shut down and start through `pve-guests`, so the cluster is down for about 5 minutes.
    - It skips the window while a UPS reports battery power, and stops without rebooting if the upgrade fails.
    - With `pve_patch_window_kernel_series` set, it pins the newest installed kernel of that series before rebooting.
    - It records a success timestamp for monitoring.

    The time avoids the UniFi firmware updates around midnight, the evening backups and the nodes' reboot window. `pve_repos_upgrade_packages=true` remains for an upgrade on demand.
3. **Kernel series.** The host stays on the 6.17 kernel series (`pve_patch_window_kernel_series: "6.17"`). Kernel 7.0, the Proxmox VE 9.2 default, is installed but not booted until it is tested on its own, because a 7.0 build was reported to panic with PCI serial ports and the AMT console uses one ([ADR-017](017-intel-amt-oob-management.md)).

### Kubernetes Nodes

1. **Daily security updates** through Ubuntu's `unattended-upgrades` defaults, unchanged. Automatic reboot stays off.
2. **Coordinated reboots** with [kured](../infrastructure/kured.md). When an update creates `/var/run/reboot-required`, kured drains the node, reboots it and uncordons it, one node at a time, between 01:30 and 03:00. It waits while any alert other than `Watchdog` is firing.

### Monitoring

The `homelab-patching` alert group ([Alerting](../infrastructure/alerting.md#patching)) reports:

- **Security updates** pending on the host for 3 days. The daily job should clear them within a day, so this leaves time to fix it within the 14-day target.
- **Stale update data**, so the patching alerts cannot fail silently.
- **A missed patch window**, after 35 days without a success.
- **A node reboot** pending for 3 days, which means kured is blocked.

## Alternatives Considered

- **Unattended full upgrades of Proxmox packages:** Proxmox recommends running `apt full-upgrade` deliberately rather than as background upgrades. The host's reboot also stops the whole cluster, so it belongs in a scheduled window.
- **Manual upgrades only:** the previous state, which left the host months behind.
- **`Unattended-Upgrade::Automatic-Reboot` on the nodes:** each node would reboot on its own schedule without draining or checking the others, possibly several at once.
- **Rebuilding node images instead of patching in place:** replacing nodes from a fresh Packer template, as managed Kubernetes services do, avoids drift. It needs automated node replacement this cluster does not have yet; kured covers in-place patching meanwhile.

## Consequences

- **Planned outage:** the cluster has an unattended outage of about 5 minutes on the first Sunday of most months, at 03:30.
- **Node reboots:** nodes reboot overnight a day after updates that need it. Rebooting node-1, the control plane, makes the API unavailable for a few minutes.
- **Firing alerts block node reboots,** so a long-firing alert delays node patching until `NodeRebootPending` reports it.
- **Pending update counts for the nodes are not collected yet.** Debian's `prometheus-node-exporter-collectors` package depends on `prometheus-node-exporter`, which would start a second exporter on the port the cluster's DaemonSet uses. Collecting them means vendoring the `apt_info.py` collector script into a node role and reading the textfile directory from the cluster's node-exporter. Until then, a stalled `unattended-upgrades` on a node shows up only through `NodeRebootPending` after the next kernel update.
- **Kernel 7.0** needs its own tested change before `pve_patch_window_kernel_series` is cleared.
