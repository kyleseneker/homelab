# SNMP Exporter

Reads the UNAS Pro's SNMPv3 agent and republishes it as Prometheus metrics: reachability, CPU, memory, load, network interfaces, fans, and board and SoC temperatures.

## Details

| Field | Value |
|-------|-------|
| Chart | `prometheus-snmp-exporter` |
| Repository | <https://prometheus-community.github.io/helm-charts> |
| Version | 9.21.0 |
| Image | `quay.io/prometheus/snmp-exporter` |
| Namespace | `monitoring` |
| Port | 9116 |
| Target | `192.168.1.158`, UDP 161 (the UNAS Pro) |
| Prometheus job | `unas-snmp`, instance `unas-pro` |
| Credentials | Vault `infrastructure/unas-snmp` (`username`, `password`) synced to Secret `unas-snmp` |

## How It Works

SNMP is enabled in the NAS's own UniFi OS settings, which offer only SNMPv3 with a username, one password, a location and a contact. The agent uses that password for both SHA authentication and AES privacy, and rejects unencrypted (`authNoPriv`) and unauthenticated requests.

The chart's ConfigMap holds the `unas_v3` auth and an `lm_sensors` module. The `system`, `if_mib`, `ucd_la_table`, `ucd_memory` and `ucd_system_stats` modules come from the `snmp.yml` bundled in the image, loaded with a second `--config.file`. `--config.expand-environment-variables` fills `${UNAS_SNMP_USERNAME}` and `${UNAS_SNMP_PASSWORD}` from the `unas-snmp` Secret, so the credentials never appear in Git or the ConfigMap.

The `unas-snmp` `ScrapeConfig` uses the multi-target exporter pattern: Prometheus sends the NAS address as the `target` parameter to the exporter's `/snmp` endpoint every 60 seconds. A failed SNMP request returns HTTP 500, so the job's `up` series drops to 0. `monitoring-egress-snmp-exporter` allows UDP 161 to the NAS only; the UniFi zone firewall already allows the Homelab zone to reach the NAS.

## What the NAS Exposes

The UNAS Pro runs the generic net-snmp agent with the UCD and LM-SENSORS tables and no Ubiquiti MIB.

| Covered | Not covered |
|---------|-------------|
| Uptime, CPU, load, memory | Drive SMART data and drive temperatures |
| Interface status and traffic | Storage pool and RAID state |
| Fans (RPM), temperatures (millidegrees C), voltages | Filesystem capacity |

Pool capacity is already visible through the kubelet's NFS volume statistics, which back `MediaLibrarySpaceLow`. Drive and pool health are available only from the UniFi Drive API, which is not scraped.

Only `fan1` and `fan2` report a speed; `fan3` and `fan4` always read 0, so `NASFanStopped` watches the first two. The temperature sensors are `temp1`, `temp3` and `Board Temp`. Alerts are listed in [Alerting](alerting.md#nas-health).

## Credentials

Store the username and password that were entered on the NAS:

```bash
SECRET_PATH=infrastructure/unas-snmp KEY=username make vault-put-secret
SECRET_PATH=infrastructure/unas-snmp KEY=password make vault-put-secret
```

To rotate, change the password on the NAS, update Vault, wait for External Secrets to refresh `unas-snmp`, then restart the exporter. It reads the environment only at startup, and the chart cannot carry Reloader's Deployment annotation:

```bash
kubectl -n monitoring rollout restart deployment/snmp-exporter-prometheus-snmp-exporter
```

## Upstream Documentation

- <https://github.com/prometheus/snmp_exporter>
- <https://github.com/prometheus-community/helm-charts/tree/main/charts/prometheus-snmp-exporter>
