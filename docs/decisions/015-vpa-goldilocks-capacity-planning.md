# ADR-015: VPA and Goldilocks for Capacity Planning

## Status

Accepted

## Context

All workloads in the cluster have manually estimated resource requests and limits. Without usage data, these are educated guesses -- potentially over-provisioned (wasting memory on a 64GB single-host cluster) or under-provisioned (risking OOM kills). There is no systematic way to know whether requests match actual consumption, or to track cluster-wide capacity headroom over time.

## Decision

Deploy the Kubernetes Vertical Pod Autoscaler (VPA) in recommend-only mode alongside Goldilocks for automated VPA CR lifecycle management. VPA analyzes historical resource usage and produces right-sizing recommendations. Goldilocks auto-creates a VPA CR for every Deployment and StatefulSet across all namespaces, and provides a web dashboard for browsing recommendations. Two custom Grafana dashboards provide cluster-wide capacity visibility.

### Components

- **VPA Recommender** (official `autoscaler/vertical-pod-autoscaler` chart): Runs in `kube-system`, computes CPU and memory recommendations based on actual usage patterns. The updater and admission controller are disabled -- no pods are ever mutated automatically.
- **Goldilocks** (Fairwinds chart): Runs in `goldilocks` namespace with `on-by-default: true`, automatically creating VPA CRs for all workloads in all namespaces (excluding `kube-node-lease` and `kube-public`). Provides a dashboard for viewing per-workload recommendations.
- **Grafana dashboards**: Cluster Capacity Overview (requested vs allocatable vs used, with utilization gauges) and Namespace Resource Breakdown (per-namespace tables with efficiency percentages, stacked timeseries).

## Alternatives Considered

- **Manual VPA CRs per workload**: More GitOps-pure since every VPA CR is explicit in the repo. However, the cluster has 28+ Deployments and 8+ StatefulSets. Maintaining individual VPA manifests that duplicate workload names creates significant boilerplate and must stay in sync as workloads are added or removed. Goldilocks eliminates this maintenance burden.
- **Fairwinds VPA Helm chart**: Was the de facto standard when no official chart existed. Now two minor versions behind upstream (1.4.1 vs 1.6.0) and maintained by a third party. The official chart is published by SIG Autoscaling to `https://kubernetes.github.io/autoscaler` and always tracks the latest upstream release.
- **VPA with updater enabled**: VPA can automatically adjust resource requests by evicting and recreating pods. On a single-host homelab with single-replica services, pod eviction causes downtime. Recommend-only mode provides the data without the disruption.
- **Prometheus queries only (no VPA)**: Raw `container_cpu_usage_seconds_total` and `container_memory_working_set_bytes` metrics are available, but VPA adds value through its recommendation algorithm that accounts for usage patterns, percentiles, and confidence intervals over time -- more sophisticated than manual eyeballing of dashboards.
- **Grafana community dashboards**: Several popular dashboards exist on grafana.com (IDs 5228, 5499, 13125). These use older panel types and lack request efficiency calculations. The built-in `k8s-resources-cluster` and `k8s-resources-namespace` dashboards from kube-prometheus-stack provide detailed drill-down views but not the high-level capacity overview with headroom gauges that operators need for planning.

## Rationale

- **Recommend-only is the right mode**: The goal is data for tuning, not automated pod disruption. With `updateMode: "Off"`, VPA writes recommendations to status fields and Prometheus metrics without touching running workloads. Operators apply changes deliberately through manifest updates.
- **Official VPA chart over Fairwinds**: The chart at `https://kubernetes.github.io/autoscaler` is maintained by SIG Autoscaling and ships app version 1.6.0. It is the upstream source. Fairwinds served the community well before the official chart existed, but there is no reason to prefer a third-party chart that lags upstream.
- **Goldilocks for automation**: Featured on the CNCF blog and recommended by AWS for right-sizing. It solves the exact problem of managing VPA CR lifecycle across a growing cluster. The `on-by-default: true` flag ensures new workloads are covered without any additional configuration.
- **Complementary dashboards**: Goldilocks answers "what should each workload request?" while the Grafana dashboards answer "how much cluster headroom remains?" and "which namespaces consume the most resources?" These are different questions requiring different views.
- **Minimal overhead**: VPA recommender (~64Mi), Goldilocks controller (~64Mi), and Goldilocks dashboard (~64Mi) total ~192Mi -- less than 0.3% of the 64GB cluster.

## Consequences

- VPA recommendations are advisory. Tuning resource requests still requires manual manifest updates and a deploy cycle. This is intentional for a single-host cluster where unexpected resource changes could cascade.
- Goldilocks creates VPA CRs for all workloads including infrastructure components managed by Helm charts. These VPA CRs are cluster state not tracked in Git. If Goldilocks is removed, the VPA CRs it created will be garbage collected.
- The Goldilocks dashboard is not exposed via HTTPRoute by default. It can be accessed via `kubectl port-forward` or an HTTPRoute can be added later.
- VPA recommendations require several hours of usage data before they stabilize. Initial recommendations should not be trusted until workloads have run through at least one full usage cycle.
- The Fairwinds Helm chart for Goldilocks is a third-party dependency. Unlike VPA (official SIG project), Goldilocks depends on Fairwinds' continued maintenance. However, it is widely adopted and actively maintained.
