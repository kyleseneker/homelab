# Proxmox Host Metrics

Prometheus scrapes node-exporter on the Proxmox host, `homelabpve01`, for the hardware the Kubernetes nodes cannot see from inside their VMs: the physical NVMe drive, the CPU package temperature, and the host's own memory and root filesystem.

## Details

| Field | Value |
|-------|-------|
| Packages | Debian `prometheus-node-exporter`, `prometheus-node-exporter-collectors`, `nvme-cli` |
| Installed by | `pve_node_exporter` Ansible role (`make pve-node-exporter`) |
| Endpoint | `192.168.10.2:9100` (Homelab VLAN only) |
| Prometheus job | `proxmox-host`, instance `homelabpve01` |
| Scrape config | `kube-prometheus-stack/proxmox-host-scrape.yml` |
| Network policy | `monitoring-egress-prometheus-proxmox` |

## How It Works

The `pve_node_exporter` role installs node-exporter from the Debian repository and binds it to the host's Homelab VLAN address. The `prometheus-node-exporter-nvme` timer from the collectors package runs `nvme smart-log` every 15 minutes and writes `nvme.prom` into node-exporter's textfile directory, `/var/lib/prometheus/node-exporter`. The package's `apt` timer also publishes pending upgrades and `node_reboot_required`.

The `ScrapeConfig` carries the `release: kube-prometheus-stack` label, which the chart's default `scrapeConfigSelector` matches, as the Blackbox `Probe` resources do. The nodes and the host share `192.168.10.0/24`, so scrapes do not cross the UniFi zone firewall; the Cilium egress policy is the only gate.

The job is not named `node-exporter`. The chart's node rules, recording rules and dashboards select `job="node-exporter"` and aggregate it into cluster capacity, which would count the hypervisor's CPU and memory on top of the VMs that consume them. The homelab node-health rules (`HighNodeCPU`, `HighNodeMemory`, `NodeRootDiskFillingUp`, `NodeDiskPressure`) select no job, so they cover the host as well. Host-specific alerts are listed in [Alerting](alerting.md#proxmox-host-health).

!!! note "Memory alerts while the restore lab runs"
    Production and lab VMs together allocate 56 of the host's 64 GB, which leaves about 3 GiB available. `HighNodeMemory` fires for `homelabpve01` while the [restore lab](../runbooks/restore-lab.md) is running. If the host runs out of memory, its OOM killer stops a VM.

!!! note "The host is the cluster's failure domain"
    Prometheus runs in a VM on this host. These alerts cover the host degrading while it runs; a host outage takes Prometheus down with it and is detected by the external Watchdog heartbeat instead.

## Not Covered

- **SATA SMART**: the collectors package's `smartmon` timer runs only when `/dev/sd*` or `/dev/hd*` exists. The host has only the NVMe drive, which the `nvme` timer covers.
- **LVM thin pool**: VM disks provision a fraction of the 1.7 TiB `local-lvm` pool, so it cannot fill. Check `lvs` before provisioning disks that approach its size.
- **UNAS Pro**: the NAS is not scraped.

## Upstream Documentation

- <https://github.com/prometheus/node_exporter>
- <https://github.com/prometheus-community/node-exporter-textfile-collector-scripts>
