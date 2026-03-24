# kube-prometheus-stack

kube-prometheus-stack provides a comprehensive cluster monitoring solution, bundling Prometheus, Grafana, Alertmanager, Node Exporter, and kube-state-metrics into a single Helm release.

## Details

| Field | Value |
|-------|-------|
| Chart | `kube-prometheus-stack` |
| Repository | <https://prometheus-community.github.io/helm-charts> |
| Version | 82.10.5 |
| Namespace | `monitoring` (CreateNamespace=true, ServerSideApply=true) |
| Sync Wave | -1 |

## Key Configuration

### Prometheus

- **Retention**: 15 days
- **Storage**: 20Gi PVC using the `nfs-client` StorageClass
- **Ingress**: `prometheus.homelab.local`
- **Service discovery**: `serviceMonitorSelector` and `podMonitorSelector` are configured to match all monitors across all namespaces, not just those created by the Helm chart.

### Grafana

- **Admin credentials**: Sourced from the ExternalSecret `grafana-admin` (synced from Vault, `admin-user` and `admin-password` keys).
- **Storage**: 2Gi PVC using `nfs-client`
- **Ingress**: `grafana.homelab.local`
- **Security context**: Runs as UID/GID 472
- **Data sources**: Loki is pre-configured as a data source pointing to `http://loki.monitoring.svc.cluster.local:3100`.

### Alertmanager

- **Ingress**: `alertmanager.homelab.local`
- **Notifications**: Slack `#alerts` channel via Incoming Webhook (see [alerting.md](alerting.md))
- **Secrets**: Webhook URL mounted from `alertmanager-slack-webhook` ExternalSecret (synced from Vault)
- **Custom rules**: Homelab-specific `PrometheusRule` in `homelab-rules.yml` (app health, infra, backups, node health)

### Node Exporter

- Enabled as a DaemonSet, exposing host-level metrics (CPU, memory, disk, network) from every node.

### kube-state-metrics

- Enabled, providing metrics about the state of Kubernetes objects (deployments, pods, nodes, etc.).

### Disabled Components

The following components are disabled because they are either not applicable or not accessible in a kubeadm-based cluster:

- `kubeProxy`
- `kubeEtcd`
- `kubeControllerManager`
- `kubeScheduler`

## Cluster Integration

The monitoring stack is the central observability platform. Applications expose metrics via `ServiceMonitor` or `PodMonitor` resources, which Prometheus automatically discovers. Grafana provides visualization dashboards and integrates with Loki for log correlation.

The stack deploys at sync wave -1, after storage (NFS provisioner at wave -2) and certificate management (cert-manager at wave -3) are ready.

## Upstream Documentation

<https://github.com/prometheus-community/helm-charts>
