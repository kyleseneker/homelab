# ADR-011: Prometheus, Grafana, Loki, and Alloy for Observability

## Status

Accepted

## Context

The cluster needs metrics collection, log aggregation, dashboarding, and alerting to monitor infrastructure health and application behavior. The solution must work on a resource-constrained single-host homelab without external cloud dependencies.

## Decision

Use the kube-prometheus-stack Helm chart (Prometheus, Grafana, Alertmanager, Node Exporter, kube-state-metrics) for metrics and alerting, Loki in single-binary mode for log storage, and Alloy as a DaemonSet log collector that ships pod logs and API server audit logs to Loki. Grafana serves as the unified dashboard for both metrics and logs.

## Alternatives Considered

- **VictoriaMetrics**: Drop-in Prometheus replacement with better compression and lower resource usage. Strong choice, but kube-prometheus-stack's bundled Grafana dashboards, alerting rules, and recording rules provide significant out-of-the-box value that would need to be recreated.
- **Thanos**: Prometheus with long-term object storage and global query view. Designed for multi-cluster or high-availability setups. Unnecessary overhead for a single-cluster homelab.
- **Promtail**: Grafana's original log shipper. Replaced by Alloy, which is Grafana's recommended successor with OpenTelemetry-compatible pipelines and the same Loki write capability.
- **Fluentd / Fluent Bit**: General-purpose log shippers. More flexible but require more configuration for Kubernetes metadata enrichment and Loki output formatting. Alloy's native Kubernetes service discovery handles this with less config.
- **Elastic Stack (EFK)**: Powerful search and analytics but extremely resource-hungry. Elasticsearch alone would consume more memory than the entire monitoring namespace budget.
- **Loki distributed mode**: Horizontally scalable with separate read/write/backend components. Requires an S3-compatible object store. Single-binary mode is sufficient for the cluster's log volume and avoids the extra complexity.

## Rationale

- **kube-prometheus-stack**: Ships with curated Grafana dashboards, Prometheus recording rules, and alerting rules for Kubernetes internals. Provides production-grade monitoring out of the box without assembling individual components.
- **Loki single-binary**: Minimal resource footprint with filesystem-backed storage on NFS. No object store required. Suitable for the cluster's log volume with 168-hour (7-day) retention.
- **Alloy as log collector**: Grafana's recommended replacement for Promtail. Provides Kubernetes pod log discovery with automatic label enrichment (namespace, pod, container) and JSON parsing for structured audit logs.
- **Unified Grafana**: One UI for metrics (Prometheus datasource) and logs (Loki datasource). Grafana is pre-configured with both datasources and Authentik SSO (ADR-010).
- **Alertmanager → Slack**: Alert routing sends severity warning+ alerts to Slack with grouping by alertname and namespace. Critical alerts suppress corresponding warnings via inhibition rules.
- **Retention sizing**: Prometheus retains 15 days of metrics in 20Gi. Loki retains 7 days of logs in 10Gi. These fit within NFS storage budget while providing enough history for troubleshooting.

## Consequences

- Prometheus and Loki store data on NFS-backed PVCs, subject to the same latency and SPOF considerations as application storage (ADR-006).
- Single-binary Loki cannot be horizontally scaled. If log volume outgrows a single instance, migration to distributed mode with an object store backend would be required.
- Some kube-prometheus-stack default scrape targets are disabled (kubeProxy, kubeEtcd, kubeControllerManager, kubeScheduler) because kubeadm's control plane configuration does not expose their metrics endpoints by default.
- ServiceMonitor and PodMonitor resources are discovered cluster-wide (`nilUsesHelmValues: false`), meaning any namespace can expose metrics to Prometheus by creating a monitor resource.
