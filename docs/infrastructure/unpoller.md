# unpoller

Reads the UniFi Network API on the Dream Router every 30 seconds and exports Wi-Fi, switch and gateway metrics to Prometheus and the controller's system log to Loki ([ADR-033](../decisions/033-network-monitoring.md)).

## Details

| Field | Value |
|-------|-------|
| Chart | `app-template` |
| Repository | <https://bjw-s-labs.github.io/helm-charts> |
| Version | 5.3.0 |
| Image | `ghcr.io/unpoller/unpoller` |
| Namespace | `monitoring` |
| Port | 9130 |
| Controller | `https://192.168.10.1`, TCP 443 |
| Prometheus job | `unpoller`, scraped every 30 seconds |
| Loki | `job="unpoller"` streams from the controller's v2 system log |
| Credentials | Vault `infrastructure/unpoller` (`api_key`) synced to Secret `unpoller` |

## What It Exports

| Area | Examples |
|------|----------|
| Radios | Channel, channel busy time (`unpoller_device_radio_channel_utilization_total_ratio`), devices per radio, transmit power |
| Extenders | Wireless uplink signal (`unpoller_device_uplink_signal_dbm`) and RSSI, uplink device and channel |
| Wi-Fi devices | Signal (`unpoller_client_radio_signal_db`), experience score (`unpoller_client_satisfaction_ratio`), retries, roams, rates, time connected |
| Switch | Per-port link speed, traffic, errors and PoE power |
| Gateway | WAN throughput, the gateway's own latency monitors (`unpoller_device_wan_monitor_latency_average_seconds`), speed tests, Smart Queues state, CPU and memory |
| All devices | Uptime, so restarts show |

The configuration lives in the chart's ConfigMap (`up.conf`). Events come only from `save_syslog`, the v2 system log; the legacy events and alarms endpoints return 404 on this firmware.

## Access to the Console

The UniFi console is a management interface, and [ADR-016](../decisions/016-vlan-segmentation.md#firewall-rules) keeps the cluster off it with one exception for unpoller:

- The gateway firewall lets the three nodes reach 192.168.10.1 on TCP 443 only ([Network Infrastructure](../architecture/network-infrastructure.md#custom-rules)).
- Pod traffic leaves the cluster from node addresses, so the `deny-gateway-console` CiliumClusterwideNetworkPolicy denies 192.168.10.1:443 to every pod except unpoller in `monitoring`, and `monitoring-egress-unpoller` allows it there ([Network Policies](network-policies.md#infrastructure-administration)).
- The API key should belong to a View Only admin, so it can read but not change the network ([Credentials](#credentials)).

unpoller pins the console's self-signed certificate (`CN=unifi.local`, valid until 2027-08-26) through `ssl_cert_paths`: it accepts that certificate and no other. When the console issues a new one, `UnpollerAbsent` fires. Replace `controller.pem` in `values.yml` with the new certificate:

```bash
echo | openssl s_client -connect 192.168.10.1:443 2>/dev/null | openssl x509
```

`skip_device_tags` is on. Each call to the device-tags endpoint leaves an HTTP/2 stream open inside UniFi OS, which slowly exhausts the console's memory ([unpoller#1119](https://github.com/unpoller/unpoller/issues/1119)).

## Credentials

Create a UniFi admin with the View Only role for the Network application, sign in as that admin, and create an API key under **Settings → Control Plane → Integrations**. Store it:

```bash
SECRET_PATH=infrastructure/unpoller KEY=api_key make vault-put-secret
```

Reloader restarts the pod when External Secrets refreshes `unpoller`. To rotate, create a new key, store it, then delete the old key in UniFi.

## Dashboards

| Dashboard | Source |
|-----------|--------|
| Network | This repository: internet availability and latency from the gateway's checks, speed tests, channel busy time, devices per radio, extender links, experience by access point, weakest devices, the controller's events from Loki and device uptime |
| UniFi-Poller: Client Insights, UAP Insights, USW Insights, USG Insights, Network Sites | [unpoller/dashboards](https://github.com/unpoller/dashboards) `v2.0.0`, commit `1c97958`, with the import placeholder pointed at the `prometheus` data source |

Alerts are listed in [Alerting](alerting.md#unifi).

## Upstream Documentation

- <https://unpoller.com>
- <https://github.com/unpoller/unpoller>
