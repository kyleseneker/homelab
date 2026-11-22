# Alloy

Alloy is a telemetry collector that runs as a DaemonSet, collecting pod logs from every node, plus the Dream Router's syslog, and shipping them to Loki for aggregation.

## Details

| Field | Value |
|-------|-------|
| Chart | `alloy` |
| Repository | <https://grafana.github.io/helm-charts> |
| Version | 1.15.0 |
| Namespace | `monitoring` (CreateNamespace=true) |

## Key Configuration

- **Controller type**: `DaemonSet` (one instance per node)
- **Resources**:
    - Requests: 50m CPU, 64Mi memory
    - Limits: 200m CPU, 192Mi memory

### Pod Log Collection Pipeline

Alloy is configured with the following pipeline stages for pod logs:

1. **discovery.kubernetes "pods"** -- selects pods with `spec.nodeName` equal to the chart's downward-API `HOSTNAME` environment variable. Each DaemonSet instance discovers only its node; without this filter every instance streams every pod's logs.
2. **discovery.relabel** -- extracts and attaches metadata labels: namespace, pod name, container name, and node name.
3. **loki.source.kubernetes** -- streams container logs through the Kubernetes API (`pods/log`); it does not mount container log files.
4. **loki.write** -- pushes log entries to Loki at `http://loki.monitoring.svc.cluster.local:3100/loki/api/v1/push`.

### Audit Log Collection Pipeline

Alloy also collects Kubernetes API server audit logs from the host filesystem:

1. **local.file_match "audit_logs"** -- watches `/var/log/kubernetes/audit/audit.log` on the host (mounted as a read-only host volume).
2. **loki.source.file** -- tails the matched audit log file.
3. **loki.process** -- parses audit events as JSON, extracting `level`, `verb`, and `user` into Loki labels.
4. **loki.write** -- ships parsed audit events to Loki with `job=kubernetes-audit` and `source=audit` labels.

### UniFi Syslog Pipeline

Alloy receives the Dream Router's activity log ([ADR-033](../decisions/033-network-monitoring.md)):

1. **loki.source.syslog "unifi"** -- listens on UDP 5514 for RFC3164 syslog and adds `job=unifi-syslog`.
2. **loki.relabel** -- keeps the sender's hostname as `host` and its syslog tag as `app`.
3. **loki.process** -- matches the CEF header (`CEF:0|Ubiquiti|UniFi Network|<version>|<event id>|<event name>|<severity>|...`) and stores `event_id`, `event_name` and `cef_severity` as structured metadata, so they add no Loki streams. Lines without a CEF header pass through unchanged.
4. **loki.write** -- ships the events to Loki.

The `alloy-syslog` Service exposes the listener at 192.168.10.202, UDP 514, pinned with the `lbipam.cilium.io/ips` annotation. It uses `externalTrafficPolicy: Local`: the node holding the L2 announcement delivers to its own Alloy pod without address translation, so `monitoring-alloy-syslog` can admit 192.168.10.1 and deny every other source outside the cluster. Every node runs an Alloy pod, so the announcing node always has a backend. Node ports are not allocated.

Loki stamps events when they arrive; the router's RFC3164 timestamps carry no year or time zone. Query them in Grafana Explore:

- `{job="unifi-syslog"}` -- every event
- `sum by (event_name) (count_over_time({job="unifi-syslog"}[1h]))` -- events per type in the last hour

## Cluster Integration

Alloy is the final piece of the logging pipeline. It depends on Loki being available to accept log data; if Alloy starts first, log shipment fails and retries until Loki becomes ready.

Logs collected by Alloy are queryable in Grafana Explore via the pre-configured Loki data source.

The custom ClusterRole grants pod/namespace discovery and `get` on `pods/log`. It intentionally omits the chart's default Secret access and node proxy/metrics access. A ServiceMonitor scrapes Alloy's own metrics. Log positions use the chart's ephemeral storage, so collector restarts can replay logs; this is not a durable audit archive.

## Upstream Documentation

<https://grafana.com/docs/alloy>
