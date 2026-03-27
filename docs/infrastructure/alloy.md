# Alloy

Alloy is a telemetry collector that runs as a DaemonSet, collecting pod logs from every node and shipping them to Loki for aggregation.

## Details

| Field | Value |
|-------|-------|
| Chart | `alloy` |
| Repository | <https://grafana.github.io/helm-charts> |
| Version | 1.6.2 |
| Namespace | `monitoring` (CreateNamespace=true) |
| Sync Wave | 0 |

## Key Configuration

- **Controller type**: `DaemonSet` (one instance per node)
- **Resources**:
    - Requests: 50m CPU, 64Mi memory
    - Limits: 192Mi memory

### Pod Log Collection Pipeline

Alloy is configured with the following pipeline stages for pod logs:

1. **discovery.kubernetes "pods"** -- discovers all running pods on the node.
2. **discovery.relabel** -- extracts and attaches metadata labels: namespace, pod name, container name, and node name.
3. **loki.source.kubernetes** -- reads container log files from the node.
4. **loki.write** -- pushes log entries to Loki at `http://loki.monitoring.svc.cluster.local:3100/loki/api/v1/push`.

### Audit Log Collection Pipeline

Alloy also collects Kubernetes API server audit logs from the host filesystem:

1. **local.file_match "audit_logs"** -- watches `/var/log/kubernetes/audit/audit.log` on the host (mounted as a read-only host volume).
2. **loki.source.file** -- tails the matched audit log file.
3. **loki.process** -- parses audit events as JSON, extracting `level`, `verb`, and `user` into Loki labels.
4. **loki.write** -- ships parsed audit events to Loki with `job=kubernetes-audit` and `source=audit` labels.

## Cluster Integration

Alloy is the final piece of the logging pipeline. It deploys at sync wave 0 -- the highest wave in the infrastructure layer -- because it depends on Loki (wave -1) being available to accept log data. If Alloy started before Loki, log shipment would fail until Loki became ready.

Logs collected by Alloy are queryable in Grafana Explore via the pre-configured Loki data source.

## Upstream Documentation

<https://grafana.com/docs/alloy>
