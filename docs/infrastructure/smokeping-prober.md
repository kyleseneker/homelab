# Smokeping Prober

Pings a fixed set of targets once a second from inside the cluster and exports round-trip time histograms and loss counters, so short lag and packet loss show up between Prometheus scrapes ([ADR-033](../decisions/033-network-monitoring.md)).

## Details

| Field | Value |
|-------|-------|
| Chart | `app-template` |
| Repository | <https://bjw-s-labs.github.io/helm-charts> |
| Version | 5.3.0 |
| Image | `quay.io/superq/smokeping-prober` |
| Namespace | `monitoring` |
| Port | 9374 |
| Prometheus job | `smokeping-prober`, scraped every 15 seconds |

## Targets

| `target` | Address | `scope` | What a problem here means |
|----------|---------|---------|---------------------------|
| `gateway` | 192.168.10.1 | `lan` | The switch, its uplink or the Dream Router |
| `nas` | 192.168.10.10 | `lan` | The switch or the NAS; same VLAN, never crosses the gateway |
| `cloudflare` | 1.1.1.1 | `internet` | The WAN link, the ISP or beyond |
| `google` | 8.8.8.8 | `internet` | |
| `quad9` | 9.9.9.9 | `internet` | |

The probes start on wired nodes, so none of them crosses Wi-Fi. Loss to every resolver while the gateway answers points at the WAN link or the ISP; loss to the gateway as well points inside the house.

Every series carries the `target` and `scope` labels from the config file, plus the prober's own `host` and `ip`.

## How It Works

Each target group sets `protocol: udp`. The prober then opens unprivileged ICMP datagram sockets, which still send ordinary echo requests. The pod sets the `net.ipv4.ping_group_range` sysctl to its group, 65534, and runs as non-root with every capability dropped, so no Kyverno PolicyException is needed. `protocol: icmp` would switch the prober to raw sockets and require `NET_RAW`.

`smokeping_requests_total` counts pings sent and the `smokeping_response_duration_seconds` histogram records each reply, so loss over a window is one minus replies over requests. The config is a ConfigMap, and Reloader restarts the pod when it changes. `monitoring-egress-smokeping-prober` allows ICMP echo to the five addresses only.

## Queries

```promql
# Median round-trip time per target
histogram_quantile(0.5, sum by (target, le) (rate(smokeping_response_duration_seconds_bucket[5m])))

# Packet loss per target
1 - sum by (target) (rate(smokeping_response_duration_seconds_count[5m]))
  / sum by (target) (rate(smokeping_requests_total[5m]))
```

The Network dashboard in Grafana shows both, the 95th percentile and a latency heatmap for the internet targets. Alerts are listed in [Alerting](alerting.md#network-reachability).

## Upstream Documentation

- <https://github.com/SuperQ/smokeping_prober>
