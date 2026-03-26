# Descheduler

The Kubernetes Descheduler runs as a CronJob and evicts pods that violate scheduling strategies, allowing the default scheduler to rebalance them across nodes. This is useful in a 2-worker-node cluster where pod distribution drifts after node reboots or deployments.

## Details

| Field | Value |
|-------|-------|
| Chart | `descheduler` |
| Repository | <https://kubernetes-sigs.github.io/descheduler/> |
| Version | 0.35.1 |
| Namespace | `kube-system` |
| Sync Wave | -1 |

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

The Descheduler respects PodDisruptionBudgets. It will not evict pods if doing so would violate a PDB constraint. The PDBs defined for Loki, Vault, and other critical services will prevent those pods from being evicted during rebalancing.

## Upstream Documentation

<https://sigs.k8s.io/descheduler>
