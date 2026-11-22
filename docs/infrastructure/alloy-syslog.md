# Alloy Syslog

A dedicated Alloy instance that receives the Dream Router's activity log over syslog and ships it to Loki as `job=unifi-syslog` ([ADR-033](../decisions/033-network-monitoring.md)). It is separate from the node-log [Alloy](alloy.md) DaemonSet because it needs an experimental feature.

## Details

| Field | Value |
|-------|-------|
| Chart | `alloy` |
| Repository | <https://grafana.github.io/helm-charts> |
| Version | 1.15.0 |
| Namespace | `monitoring` |
| Controller | Deployment, one replica |
| Listener | `alloy-syslog-udp` Service, 192.168.10.202 UDP 514, to container port 5514 |
| Stability level | `experimental` |
| Prometheus job | `alloy-syslog` |

## Message Format

The router sends one CEF event per UDP datagram, without the syslog priority header:

```text
Nov 22 17:40:36 Dream-Router-7 CEF:0|Ubiquiti|UniFi Network|10.6.109|203|Blocked by Firewall|4|UNIFIcategory=Security ...
```

Alloy's `rfc3164` and `rfc5424` parsers reject a message that does not start with `<PRI>`, so `loki.source.syslog` uses the experimental `raw` format, which requires `--stability.level=experimental`. Keeping it in its own instance leaves the node-log DaemonSet at generally available.

## Pipeline

1. **loki.source.syslog "unifi"** -- listens on UDP 5514 in `raw` format and adds `job=unifi-syslog`.
2. **loki.process "unifi"** -- splits the timestamp and hostname from the message, keeps the hostname as the `host` label, and stores `event_id`, `event_name` and `cef_severity` from the CEF header as structured metadata, so they add no Loki streams. The stored line starts at `CEF:`. Lines without a CEF header keep only `host`.
3. **loki.write** -- pushes to Loki.

Loki stamps events when they arrive; the router's timestamps carry no year or time zone.

## Network Path

The `alloy-syslog-udp` Service pins its address with the `lbipam.cilium.io/ips` annotation and uses `externalTrafficPolicy: Local`. Cilium announces the address only from the node running the pod, which receives the datagrams without address translation, so `monitoring-alloy-syslog` admits 192.168.10.1 on UDP 5514 and denies every other source outside the cluster ([Network Policies](network-policies.md)). When the pod moves, the announcement follows it; datagrams sent in between are lost. Node ports are not allocated.

The router's destination is set in the UniFi UI ([Network Infrastructure](../architecture/network-infrastructure.md#syslog)).

## Security

The container runs as UID 473 with a read-only root filesystem, no capabilities and an `emptyDir` at `/tmp/alloy` for its storage path. The chart's RBAC is disabled, because the pipeline never calls the Kubernetes API, and anonymous usage reporting is off.

## Queries

- `{job="unifi-syslog"}` -- every event
- `sum by (event_name) (count_over_time({job="unifi-syslog"}[1h]))` -- events per type in the last hour
- `{job="unifi-syslog"} | event_name="Blocked by Firewall"` -- one event type

`loki_source_syslog_entries_total` and the component's warnings in the pod log show whether messages arrive and parse.

## Upstream Documentation

- <https://grafana.com/docs/alloy/latest/reference/components/loki/loki.source.syslog/>
