# Goldilocks

Goldilocks automatically creates VPA objects for all workloads in the cluster and provides a web dashboard for browsing right-sizing recommendations. It works alongside the [VPA recommender](vpa.md) to surface per-workload CPU and memory tuning data.

## Details

| Field | Value |
|-------|-------|
| Chart | `goldilocks` |
| Repository | <https://charts.fairwinds.com/stable> |
| Version | 10.3.0 |
| Namespace | `goldilocks` |

## Key Configuration

- **Auto-discovery**: `on-by-default: true` -- the controller monitors all namespaces without requiring individual namespace labels
- **Excluded namespaces**: `kube-node-lease`, `kube-public`
- **Dashboard**: Single replica for browsing recommendations
- **VPA sub-chart**: Disabled (`vpa.enabled: false`). VPA is installed separately via the official SIG Autoscaling chart.

### Resources

| Component | CPU Request | Memory Request | Memory Limit |
|-----------|------------|---------------|-------------|
| Controller | 25m | 64Mi | 256Mi |
| Dashboard | 15m | 64Mi | 128Mi |

## How It Works

1. The Goldilocks controller watches all namespaces (except excluded ones) for Deployments and StatefulSets
2. For each workload found, it creates a `VerticalPodAutoscaler` CR with `updateMode: "Off"`
3. The VPA recommender picks up these CRs and computes recommendations
4. The Goldilocks dashboard aggregates recommendations into a per-namespace, per-workload view

When workloads are added or removed, Goldilocks creates or deletes the corresponding VPA CRs automatically.

## Accessing the Dashboard

The Goldilocks dashboard is exposed via Gateway API HTTPRoute at `https://goldilocks.homelab.local`.

## Cluster Integration

Goldilocks depends on the VPA recommender being installed and running. It does not require the VPA updater or admission controller.

The controller creates VPA CRs as cluster state that is not tracked in Git. If Goldilocks is uninstalled, its VPA CRs are garbage collected.

## Upstream Documentation

<https://goldilocks.docs.fairwinds.com/>
