# Kyverno

Kyverno is a Kubernetes-native policy engine that validates, mutates, and generates resources using admission webhooks. It runs as a set of controllers in the `kyverno` namespace and evaluates policies against incoming API requests.

## Details

| Field | Value |
|-------|-------|
| Chart | `kyverno` |
| Repository | <https://kyverno.github.io/kyverno/> |
| Version | 3.9.2 |
| Namespace | `kyverno` |

## Key Configuration

- **Admission Controller**: 3 replicas, one per node including the control plane, with a `maxUnavailable: 1` PDB. Required anti-affinity keeps a drained node's replica Pending until that node returns, so the fail-closed webhook keeps two replicas through each drain and the spread restores itself. Rollouts replace pods in place (`maxSurge: 0`) because no node has room for a surge replica.
- **Resources** (across all controllers):
    - Requests: ~250m CPU, ~320Mi memory
    - Limits: ~896Mi memory
- **Validation Mode**: Enforce (non-compliant pods are rejected at admission)

## Policies

Policies are deployed as `ClusterPolicy` resources via a separate ArgoCD Application (`kyverno-policies`). All policies run in **Enforce** mode -- non-compliant pods are rejected at admission time.

Kyverno 1.19 deprecates `ClusterPolicy`. Each policy has an equivalent `ValidatingPolicy` (`policies.kyverno.io/v1`, same name, `*.vpol.yml`) that runs beside it in Audit mode with `failurePolicy: Ignore`, so it records results without affecting admission while its reports are compared with the legacy policy's. The ValidatingPolicies autogenerate rules for the same pod controllers, exclude the same namespaces, and match `cilium-test-*` through `namespaceObject`, because autogen rewrites `object.metadata` for controllers. At cutover they switch to `Deny` with `failurePolicy: Fail`, matching the fail-closed legacy webhooks, and the `ClusterPolicy` files are removed.

| Policy | What It Checks | Excluded Namespaces |
|--------|----------------|---------------------|
| `require-resource-limits` | All containers have CPU and memory limits | backups, local-path-storage |
| `require-run-as-nonroot` | Containers set `runAsNonRoot: true` | arr, auth, backups, intel-gpu-operator, monitoring, nfs-provisioner, local-path-storage |
| `require-readonly-rootfs` | Containers set `readOnlyRootFilesystem: true` | arr, auth, backups, monitoring, nfs-provisioner, local-path-storage |
| `disallow-latest-tag` | Images use a non-latest tag or SHA-256 digest | |
| `require-labels` | Pods have the `app.kubernetes.io/name` label | backups, intel-gpu-operator, nfs-provisioner |

All policies also exclude the base system namespaces: kube-system, kyverno, argocd, and cilium-test-*.

Image tags and security contexts are checked on regular, init and ephemeral containers. Resource limits apply to regular and init containers; Kubernetes does not permit resources on ephemeral containers. Namespace exclusions also exempt unrelated workloads sharing those namespaces and should be narrowed after a rendered-workload audit.

### Namespace Exclusions

Exclusions exist for workloads where compliance is not feasible:

- **arr, auth**: linuxserver and Authentik images require root and writable root filesystems (s6-overlay init system)
- **backups**: Velero dynamically creates backup/restore/maintenance Job pods with specs we do not control
- **intel-gpu-operator**: GPU device plugin DaemonSet requires host-level access
- **monitoring**: Alloy requires root for reading host log files
- **nfs-provisioner**: Requires host-level access for NFS mounts

### Local Regression Checks

`tests/kyverno/container-security` covers valid pods and denied init/ephemeral container bypasses, including an image registry port that must not be mistaken for an image tag, and the `app.kubernetes.io/name` label. `tests/kyverno/container-security-cel` runs the same cases and expectations against the ValidatingPolicies. Run both with the Kyverno CLI matching the chart application version (currently 1.19.2):

```bash
kyverno test tests/kyverno
```

Before enabling stronger checks, also apply the policies locally to rendered workload manifests with their destination namespaces. Include init containers from dependency charts; admission failures can otherwise block upgrades. Helm test hooks are a separate test execution concern.

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
