# Reloader

Reloader watches for changes to ConfigMaps and Secrets referenced by Deployments, StatefulSets, and DaemonSets, and triggers rolling restarts when they change. This eliminates the need to manually restart pods after updating secrets or config values.

## Details

| Field | Value |
|-------|-------|
| Chart | `reloader` |
| Repository | <https://stakater.github.io/stakater-charts> |
| Version | 2.2.9 |
| Namespace | `kube-system` |

## Key Configuration

- **watchGlobally**: `true` -- monitors resources across all namespaces, not just its own.
- **Resources**:
    - Requests: 25m CPU, 32Mi memory
    - Limits: 128Mi memory

## How It Works

When a ConfigMap or Secret changes, Reloader detects the update and triggers a rolling restart of an opted-in workload that references it. This is particularly useful with External Secrets Operator -- when a secret is rotated in Vault, ESO syncs the updated value to the K8s Secret, and Reloader automatically restarts the affected pods to pick up the new values.

`watchGlobally` controls namespace scope, not opt-in. Workload metadata must include `reloader.stakater.com/auto: "true"` (or a specific Secret/ConfigMap reload annotation). `autoReloadAll` is not enabled. Several application charts already set this annotation; infrastructure workloads without it require their own reload mechanism or an explicit rollout after credential rotation. Verify the rendered Deployment/StatefulSet annotation, not just a Helm value.

## Upstream Documentation

<https://github.com/stakater/Reloader>
