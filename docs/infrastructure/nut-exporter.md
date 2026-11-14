# NUT Exporter

Exposes UPS telemetry to Prometheus by querying the NUT (Network UPS Tools) server running on the Proxmox host.

## Details

| Field | Value |
|-------|-------|
| Chart | `app-template` |
| Repository | <https://bjw-s-labs.github.io/helm-charts> |
| Version | 5.3.0 |
| Image | `ghcr.io/druggeri/nut_exporter` |
| Namespace | `monitoring` |
| Metrics port | 9199 |
| NUT server | `192.168.10.2:3493` (the Proxmox host) |

## How It Works

The CyberPower CP1500PFCRM2U connects to the MS-01 over USB-B. The `pve_ups` Ansible role (`make pve-ups`) configures `usbhid-ups` and the NUT server on the Proxmox host; this exporter scrapes that server over the network and republishes the readings as Prometheus metrics via a ServiceMonitor.

Metrics include battery charge, estimated runtime, load percentage, and input voltage -- enough to alert on both a power event and on the UPS itself degrading.

!!! note "The exporter is outside the failure domain it monitors"
    The UPS is attached to the hypervisor, not to the cluster. If the Proxmox host is down, the exporter cannot scrape it and the series disappears rather than reporting a bad value. Alerts on this data need `absent()` to catch that, not a threshold.

The UPS fails about one in six USB report reads, spread across all report IDs, and `usbhid-ups` reconnects after each failure (roughly every 12 seconds). Most reconnects go unnoticed. 50-80 times a day the reopen also fails and upsd marks the data stale for a few seconds, so short scrape failures are normal and alerting thresholds have to tolerate them. The same failures can make the driver need several attempts to start (`Can't initialize data from HID UPS`); systemd retries it every 15 seconds. The failures are a CyberPower firmware fault during back-to-back requests. NUT releases before 2.8.5 reconnect on every transient I/O error, and 2.8.1 reports it as `Resource temporarily unavailable` because it passes a stale errno; 2.8.5 skips the failing report instead ([nut#3116](https://github.com/networkupstools/nut/issues/3116)). Debian trixie ships 2.8.1. `pollonly`, `pollinterval` and `pollfreq` do not help.

## Upstream Documentation

<https://github.com/DRuggeri/nut_exporter>
