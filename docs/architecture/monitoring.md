# Monitoring & Observability

This document covers the full monitoring and observability stack, including metrics collection, log aggregation, visualization, and alerting.

## Observability Stack Overview

The monitoring stack provides two parallel data pipelines -- one for metrics and one for logs -- converging in Grafana for unified visualization.

```mermaid
flowchart LR
    subgraph metricsPath["Metrics Pipeline"]
        nodeExp["Node Exporter"] --> prometheus["Prometheus"]
        ksm["kube-state-metrics"] --> prometheus
        kubelet["Kubelet /metrics"] --> prometheus
    end

    subgraph logsPath["Logs Pipeline"]
        pods["Application Pods"] --> alloy["Alloy\n(DaemonSet)"]
        alloy --> loki["Loki\n(single-binary)"]
    end

    subgraph visualization["Visualization & Alerting"]
        prometheus --> grafana["Grafana"]
        loki --> grafana
        prometheus --> alertmanager["Alertmanager"]
    end
```

## Component Inventory

| Component | Purpose | Deployment | Storage |
|-----------|---------|-----------|---------|
| Prometheus | Metrics collection, storage, and rule evaluation | StatefulSet | 20Gi PVC (`nfs-client`), 15d retention |
| Grafana | Dashboards and visualization for metrics and logs | Deployment | Persistent PVC (`nfs-client`) |
| Alertmanager | Alert routing, grouping, and notification | StatefulSet | Ephemeral |
| Node Exporter | Host-level hardware and OS metrics | DaemonSet | None |
| kube-state-metrics | Kubernetes object state metrics | Deployment | None |
| Loki | Log aggregation and querying | StatefulSet (single-binary) | 10Gi PVC (`nfs-client`), 168h retention |
| Alloy | Pod log collection and shipping | DaemonSet | None (streams to Loki) |
| Exportarr | Prometheus metrics exporter for *arr apps | Multi-Deployment (one per target) | None |
| Uptime Kuma | Synthetic HTTP/TCP/DNS monitoring | Deployment | 1Gi PVC (`nfs-client`) |

## Metrics Pipeline

### Prometheus

Prometheus is deployed via the `kube-prometheus-stack` Helm chart (sync wave -1) and serves as the central metrics store.

| Setting | Value |
|---------|-------|
| Retention | 15 days |
| Storage | 20Gi PVC (`nfs-client`) |
| Access | `prometheus.homelab.local` |
| Sync Wave | -1 |

Prometheus scrapes metrics from:

- **Node Exporter** -- CPU, memory, disk, network, and other host-level metrics from every node
- **kube-state-metrics** -- Kubernetes object states (pod status, deployment replicas, node conditions)
- **Kubelet metrics** -- Container resource usage and pod lifecycle events
- **Exportarr** -- *arr application metrics (queue depth, library size, missing episodes) via ServiceMonitors
- **Application metrics** -- Any pods with Prometheus scrape annotations

### Alertmanager

Alertmanager receives alerts from Prometheus and handles deduplication, grouping, silencing, and routing.

| Setting | Value |
|---------|-------|
| Access | `alertmanager.homelab.local` |
| Deployment | Part of kube-prometheus-stack |

### Node Exporter

Node Exporter runs as a DaemonSet, ensuring one instance per node. It exposes host-level metrics including:

- CPU utilization and load averages
- Memory and swap usage
- Disk I/O and filesystem capacity
- Network interface statistics
- System temperature (where available)

### kube-state-metrics

kube-state-metrics generates metrics about Kubernetes object states by listening to the Kubernetes API server. Key metrics include:

- Pod phase and container status
- Deployment and StatefulSet replica counts
- PersistentVolume and PVC status
- Node conditions and resource capacity

## Logs Pipeline

### Loki

Loki runs in **single-binary mode**, combining all Loki components (distributor, ingester, querier, compactor) in a single process. This simplifies deployment for a homelab-scale cluster.

| Setting | Value |
|---------|-------|
| Mode | Single-binary (monolithic) |
| Retention | 168 hours (7 days) |
| Storage | 10Gi PVC (`nfs-client`), filesystem backend |
| Access | Via Grafana data source |
| Sync Wave | -1 |

!!! info "Filesystem Backend"
    Loki uses the local filesystem (backed by NFS PVC) for chunk and index storage. This avoids the need for an external object store while providing persistence across pod restarts.

### Alloy

Alloy is Grafana's OpenTelemetry-compatible collector, deployed as a **DaemonSet** to collect logs from every node. It replaced Promtail as the recommended log collector.

| Setting | Value |
|---------|-------|
| Deployment | DaemonSet |
| Source | Pod logs via Kubernetes discovery |
| Destination | Loki |
| Sync Wave | 0 |

#### Alloy Pipeline Configuration

Alloy uses a pipeline-based configuration that discovers, filters, relabels, and ships logs:

```mermaid
flowchart LR
    discovery["Kubernetes\nPod Discovery"] --> relabel["Relabel\n(namespace, pod,\ncontainer, node)"]
    relabel --> logScrape["Log Scrape\n(pod stdout/stderr)"]
    logScrape --> lokiWrite["Loki Write\nEndpoint"]
```

1. **Discovery:** Alloy uses the Kubernetes discovery mechanism to find all running pods on the node
2. **Relabeling:** Extracts and attaches metadata labels:
    - `namespace` -- Kubernetes namespace
    - `pod` -- Pod name
    - `container` -- Container name
    - `node` -- Node the pod is running on
3. **Log scrape:** Reads `stdout`/`stderr` log streams from discovered pods
4. **Loki write:** Ships labeled log entries to Loki's push API

## Grafana

Grafana provides a unified interface for exploring both metrics (Prometheus) and logs (Loki).

| Setting | Value |
|---------|-------|
| Access | `grafana.homelab.local` |
| Storage | Persistent PVC (`nfs-client`) |
| Admin Credentials | Sealed Secret (`grafana-admin`) |

### Pre-Configured Data Sources

| Data Source | Type | Purpose |
|------------|------|---------|
| Prometheus | Metrics | Default metrics data source for dashboards |
| Loki | Logs | Log exploration and correlation with metrics |

Grafana is deployed with both data sources pre-configured via Helm values, eliminating manual setup after deployment.

!!! tip "Log Correlation"
    Use Grafana's split view to correlate metrics spikes with log entries. Select a time range on a Prometheus dashboard panel and switch to the Explore view with Loki to see logs from the same period.

## Data Flow Summary

```mermaid
flowchart TD
    subgraph nodes["Cluster Nodes"]
        ne["Node Exporter"]
        alloyDs["Alloy DaemonSet"]
        appPods["Application Pods"]
    end

    subgraph monitoring["monitoring Namespace"]
        prom["Prometheus\n15d retention\n20Gi"]
        loki["Loki\n168h retention\n10Gi"]
        grafana["Grafana"]
        am["Alertmanager"]
        ksm["kube-state-metrics"]
    end

    ne -->|"host metrics"| prom
    ksm -->|"k8s object metrics"| prom
    appPods -->|"scrape annotations"| prom
    appPods -->|"stdout/stderr"| alloyDs
    alloyDs -->|"labeled logs"| loki
    prom -->|"metrics queries"| grafana
    loki -->|"log queries"| grafana
    prom -->|"alerting rules"| am

    subgraph arr["arr Namespace"]
        exportarr["Exportarr\n(ServiceMonitors)"]
        arrApps["Sonarr, Radarr,\nProwlarr, Bazarr"]
    end

    arrApps -->|"API"| exportarr
    exportarr -->|"arr metrics"| prom
```
