# Descheduler

The Kubernetes Descheduler runs as a CronJob and evicts pods that violate scheduling strategies, allowing the default scheduler to rebalance them across nodes. This is useful in a 2-worker-node cluster where pod distribution drifts after node reboots or deployments.

## Details

| Field | Value |
|-------|-------|
| Chart | `descheduler` |
| Repository | <https://kubernetes-sigs.github.io/descheduler/> |
| Version | 0.36.0 |
| Namespace | `kube-system` |

## Key Configuration

- **Schedule**: Every 30 minutes (`*/30 * * * *`)
- **Resources**:
    - Requests: 25m CPU, 64Mi memory
    - Limits: 128Mi memory

### Strategies

| Plugin | Type | Purpose |
|--------|------|---------|
| `RemoveDuplicates` | Balance | Evicts duplicate pods from the same node (excludes DaemonSets) |
| `LowNodeUtilization` | Balance | Rebalances pods when node utilization is below 20% CPU/memory/pods, targeting nodes above 50% |
| `RemovePodsHavingTooManyRestarts` | Deschedule | Evicts pods with more than 10 restarts (including init containers) |

## Interaction with PDBs

The Descheduler respects PodDisruptionBudgets. It will not evict pods if doing so would violate a PDB constraint. Single-replica services such as Loki and Vault use `maxUnavailable: 1` so their PDBs never block a node drain; they limit evictions to one pod at a time but do not prevent them.

## Versioning

Each descheduler minor is built against the matching Kubernetes minor (0.36 for 1.36). Renovate holds the chart within one minor of the cluster; raise the `allowedVersions` cap in `renovate.json` with each Kubernetes upgrade.

## Upstream Documentation

<https://sigs.k8s.io/descheduler>
