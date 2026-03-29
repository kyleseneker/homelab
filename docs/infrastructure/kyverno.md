# Kyverno

Kyverno is a Kubernetes-native policy engine that validates, mutates, and generates resources using admission webhooks. It runs as a set of controllers in the `kyverno` namespace and evaluates policies against incoming API requests.

## Details

| Field | Value |
|-------|-------|
| Chart | `kyverno` |
| Repository | <https://kyverno.github.io/kyverno/> |
| Version | 3.7.1 |
| Namespace | `kyverno` |
| Sync Wave | -2 |

## Key Configuration

- **Admission Controller**: 1 replica
- **Resources** (across all controllers):
    - Requests: ~250m CPU, ~320Mi memory
    - Limits: ~896Mi memory
- **Validation Mode**: Enforce (non-compliant pods are rejected at admission)

## Policies

Policies are deployed as `ClusterPolicy` resources via a separate ArgoCD Application (`kyverno-policies`) at sync wave -1. All policies run in **Enforce** mode -- non-compliant pods are rejected at admission time.

| Policy | What It Checks | Excluded Namespaces |
|--------|----------------|---------------------|
| `require-resource-limits` | All containers have CPU and memory limits | backups |
| `require-run-as-nonroot` | Containers set `runAsNonRoot: true` | arr, auth, backups, intel-gpu-operator, monitoring, nfs-provisioner |
| `require-readonly-rootfs` | Containers set `readOnlyRootFilesystem: true` | arr, auth, backups, monitoring, nfs-provisioner |
| `disallow-latest-tag` | Images use a specific tag, not `:latest` | |
| `require-labels` | Pods have the `app.kubernetes.io/name` label | backups, intel-gpu-operator, nfs-provisioner |

All policies also exclude the base system namespaces: kube-system, kyverno, argocd, metallb-system, and cilium-test-*.

### Namespace Exclusions

Exclusions exist for workloads where compliance is not feasible:

- **arr, auth**: linuxserver and Authentik images require root and writable root filesystems (s6-overlay init system)
- **backups**: Velero dynamically creates backup/restore/maintenance Job pods with specs we do not control
- **intel-gpu-operator**: GPU device plugin DaemonSet requires host-level access
- **monitoring**: Alloy requires root for reading host log files
- **nfs-provisioner**: Requires host-level access for NFS mounts

### Checking Policy Reports

To see which workloads violate policies (background scan results):

```bash
kubectl get policyreport -A
```

## Network Policies

Kyverno has its own CiliumNetworkPolicy rules:

- **Ingress**: Default deny from world; allow from cluster, kube-apiserver, and host (required for webhook calls)
- **Egress**: DNS, intra-namespace, and kube-apiserver only

## Architecture

Kyverno deploys four controllers:

| Controller | Purpose |
|------------|---------|
| Admission Controller | Intercepts API requests and evaluates policies |
| Background Controller | Scans existing resources against policies |
| Cleanup Controller | Manages resource cleanup based on policy TTLs |
| Reports Controller | Generates and manages policy reports |

## Upstream Documentation

<https://kyverno.io/docs/>
