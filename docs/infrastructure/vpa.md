# Vertical Pod Autoscaler (VPA)

The Vertical Pod Autoscaler analyzes historical pod resource usage and produces CPU and memory right-sizing recommendations. It runs in recommend-only mode -- no pods are ever mutated automatically.

## Details

| Field | Value |
|-------|-------|
| Chart | `vertical-pod-autoscaler` |
| Repository | <https://kubernetes.github.io/autoscaler> |
| Version | 0.8.1 |
| Namespace | `kube-system` |

## Key Configuration

- **Mode**: Recommend-only. The updater and admission controller are disabled. Only the recommender component runs.
- **Replicas**: 1 (default is 2, reduced for homelab scale)
- **Resources**:
    - Requests: 25m CPU, 64Mi memory
    - Limits: 256Mi memory

### How Recommendations Work

The recommender watches pods that have a corresponding `VerticalPodAutoscaler` CR and:

1. Collects CPU and memory usage from the Metrics API
2. Computes target, lower bound, and upper bound recommendations using percentile-based algorithms
3. Writes recommendations to the VPA object's `.status.recommendation` field
4. Exposes `vpa_status_recommendation` Prometheus metrics

Recommendations stabilize after several hours of usage data. Initial values should be treated as preliminary.

## VPA CR Lifecycle

VPA CRs are not managed manually. [Goldilocks](goldilocks.md) automatically creates and manages a VPA CR (with `updateMode: "Off"`) for every Deployment and StatefulSet in the cluster.

## Applying Recommendations

VPA recommendations are advisory. To act on them:

1. Check the Goldilocks dashboard or query `vpa_status_recommendation` in Grafana
2. Compare the VPA target with the current request in the workload's `values.yaml`
3. Update the manifest and let ArgoCD sync the change

## Upstream Documentation

<https://github.com/kubernetes/autoscaler/tree/master/vertical-pod-autoscaler>
