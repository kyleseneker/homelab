# kube-prometheus-stack

kube-prometheus-stack provides a comprehensive cluster monitoring solution, bundling Prometheus, Grafana, Alertmanager, Node Exporter, and kube-state-metrics into a single Helm release.

## Details

| Field | Value |
|-------|-------|
| Chart | `kube-prometheus-stack` |
| Repository | <https://prometheus-community.github.io/helm-charts> |
| Version | 92.17.0 |
| Namespace | `monitoring` (CreateNamespace=true, ServerSideApply=true) |

## Key Configuration

### Prometheus

- **Retention**: 15 days or 15GB of persisted blocks, whichever limit is reached first (WAL/head need extra space)
- **Storage**: 20Gi PVC using the `local-path` StorageClass; node-pinned and without a filesystem quota
- **Ingress**: `prometheus.home.seneker.io`
- **Service discovery**: `serviceMonitorSelector` and `podMonitorSelector` are configured to match all monitors across all namespaces, not just those created by the Helm chart.

### Grafana

- **Admin credentials**: Sourced from the ExternalSecret `grafana-admin` (synced from Vault, `admin-user` and `admin-password` keys).
- **Storage**: 2Gi PVC using `nfs-client`
- **Ingress**: `grafana.home.seneker.io`
- **Security context**: Runs as UID/GID 472
- **Data sources**: Loki is pre-configured as a data source pointing to `http://loki.monitoring.svc.cluster.local:3100`.

### Alertmanager

- **Ingress**: `alertmanager.home.seneker.io`
- **Notifications**: Slack `#alerts` channel via Incoming Webhook (see [alerting.md](alerting.md))
- **Secrets**: Webhook URL mounted from `alertmanager-slack-webhook` ExternalSecret (synced from Vault)
- **Custom rules**: Homelab-specific `PrometheusRule` in `homelab-rules.yml` (app health, infra, backups, node health)

### Node Exporter

- Enabled as a DaemonSet, exposing host-level metrics (CPU, memory, disk, network) from every node.

### kube-state-metrics

- Enabled, providing metrics about the state of Kubernetes objects (deployments, pods, nodes, etc.).

### Custom Dashboards

Two capacity planning dashboards are provisioned via sidecar ConfigMaps (label `grafana_dashboard: "1"`):

| Dashboard | Description |
|-----------|-------------|
| Cluster Capacity Overview | CPU/memory requested vs allocatable vs used, utilization gauges, pod count, namespace pie charts |
| Namespace Resource Breakdown | Per-namespace tables with requests, limits, usage, efficiency %, stacked usage timeseries |

These complement the built-in kube-prometheus-stack dashboards, which focus on detailed drill-down views rather than high-level capacity planning.

### Disabled Components

The following scrapes are disabled. kube-proxy is absent because Cilium replaces it; etcd, scheduler and controller-manager need explicit secure scrape configuration, which remains a monitoring gap:

- `kubeProxy`
- `kubeEtcd`
- `kubeControllerManager`
- `kubeScheduler`

## Cluster Integration

The monitoring stack is the central observability platform. Applications expose metrics via `ServiceMonitor` or `PodMonitor` resources, which Prometheus automatically discovers. Grafana provides visualization dashboards and integrates with Loki for log correlation.

The API server reaches the operator's admission webhook on TCP 10250 through `monitoring-allow-operator-webhook`; this permits rule validation and mutation during both apply and Argo CD server-side diff. The rule includes Cilium's `remote-node` identity because control-plane traffic can use the node's Cilium internal address.

The stack depends on local-path for Prometheus and NFS for Grafana and on cert-manager for the Gateway certificate.

## Upgrades

Take chart majors one at a time and read each section of the upstream `UPGRADE.md`. Argo CD applies the CRDs from the chart with server-side apply, so the manual `kubectl apply` CRD steps in that guide are not needed.

- **Grafana 13 (chart 84)** migrated folders and dashboards into unified storage on first start. Downgrading needs the pre-upgrade database. The SQLite database lives on NFS, so `grafana.ini` sets `unified_storage.migration_parquet_buffer` to avoid lock contention during that migration.
- **Distroless images:** Prometheus (chart 85) and Grafana (chart 89) images have no shell or `wget`, and Grafana's root filesystem is read-only. Query Prometheus through the API server instead of `kubectl exec`, as `scripts/check-alert-metrics.sh` does: `kubectl get --raw /api/v1/namespaces/monitoring/services/kube-prometheus-stack-prometheus:http-web/proxy/api/v1/query?query=up`.
- Grafana's update checker and plugin installer log timeouts reaching grafana.com, because egress to the internet is blocked. They are harmless.

## Upstream Documentation

<https://github.com/prometheus-community/helm-charts>
