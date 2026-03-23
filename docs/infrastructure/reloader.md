# Reloader

Reloader watches for changes to ConfigMaps and Secrets referenced by Deployments, StatefulSets, and DaemonSets, and triggers rolling restarts when they change. This eliminates the need to manually restart pods after updating sealed secrets or config values.

## Details

| Field | Value |
|-------|-------|
| Chart | `reloader` |
| Repository | <https://stakater.github.io/stakater-charts> |
| Version | 2.2.9 |
| Namespace | `kube-system` |
| Sync Wave | -1 |

## Key Configuration

- **watchGlobally**: `true` -- monitors resources across all namespaces, not just its own.
- **Resources**:
    - Requests: 25m CPU, 32Mi memory
    - Limits: 128Mi memory

## How It Works

When a ConfigMap or Secret changes, Reloader detects the update and triggers a rolling restart of any workload that references it. This is particularly useful with Sealed Secrets -- when a sealed secret is re-encrypted and pushed via Git, ArgoCD syncs the new SealedSecret, the controller decrypts it, and Reloader automatically restarts the affected pods to pick up the new values.

No per-workload annotations are required when `watchGlobally` is enabled. Reloader tracks all resource references automatically.

## Upstream Documentation

<https://github.com/stakater/Reloader>
