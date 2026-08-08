# NUT Exporter

Exposes UPS telemetry to Prometheus by querying the NUT (Network UPS Tools) server running on the Proxmox host.

## Details

| Field | Value |
|-------|-------|
| Chart | `app-template` |
| Repository | <https://bjw-s-labs.github.io/helm-charts> |
| Version | 4.6.2 |
| Image | `ghcr.io/druggeri/nut_exporter` |
| Namespace | `monitoring` |
| Metrics port | 9199 |
| NUT server | `192.168.10.2:3493` (the Proxmox host) |

## How It Works

The CyberPower CP1500PFCRM2U connects to the MS-01 over USB-B. The `pve_ups` Ansible role configures `usbhid-ups` and the NUT server on the Proxmox host; this exporter scrapes that server over the network and republishes the readings as Prometheus metrics via a ServiceMonitor.

Metrics include battery charge, estimated runtime, load percentage, and input voltage -- enough to alert on both a power event and on the UPS itself degrading.

!!! note "The exporter is outside the failure domain it monitors"
    The UPS is attached to the hypervisor, not to the cluster. If the Proxmox host is down, the exporter cannot scrape it and the series disappears rather than reporting a bad value. Alerts on this data need `absent()` to catch that, not a threshold.

The `usbhid-ups` driver loses the device roughly 35 times a day. The shutdown path works, but the gaps mean short scrape failures are normal and alerting thresholds have to tolerate them.

## Upstream Documentation

<https://github.com/DRuggeri/nut_exporter>
