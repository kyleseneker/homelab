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

The CyberPower CP1500PFCRM2U connects to the MS-01 over USB-B. The `pve_ups` Ansible role (`make pve-ups`) installs NUT 2.8.5 from a [signed APT repository](../decisions/031-nut-backport.md) and configures `usbhid-ups` and the NUT server on the Proxmox host; this exporter scrapes that server over the network and republishes the readings as Prometheus metrics via a ServiceMonitor.

Metrics include battery charge, estimated runtime, load percentage, and input voltage -- enough to alert on both a power event and on the UPS itself degrading.

!!! note "The exporter is outside the failure domain it monitors"
    The UPS is attached to the hypervisor, not to the cluster. If the Proxmox host is down, the exporter cannot scrape it and the series disappears rather than reporting a bad value. Alerts on this data need `absent()` to catch that, not a threshold.

The UPS fails some USB report reads when the driver sends them back to back, about 25 a minute, logged as `nut_libusb_get_report: Input/Output Error`. NUT 2.8.5 skips a failed read and keeps that value from the previous update. Releases before 2.8.5 reconnected after every failure, and 50-80 times a day the reopen also failed and the data went stale. A failed report descriptor read at startup makes the driver exit, and systemd starts it again after 15 seconds. `pollonly`, `pollinterval` and `pollfreq` do not reduce the failures. Raising the driver's debug level does, because the logging spaces out the requests.

## Upstream Documentation

<https://github.com/DRuggeri/nut_exporter>
