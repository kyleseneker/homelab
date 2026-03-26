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
- **Validation Mode**: Audit (no requests are blocked)

## Policies

Policies are deployed as `ClusterPolicy` resources via a separate ArgoCD Application (`kyverno-policies`) at sync wave -1. All policies run in **Audit** mode -- they generate policy reports but do not reject workloads.

| Policy | What It Checks |
|--------|----------------|
| `require-resource-limits` | All containers have CPU and memory limits |
| `require-run-as-nonroot` | Containers set `runAsNonRoot: true` |
| `require-readonly-rootfs` | Containers set `readOnlyRootFilesystem: true` |
| `disallow-latest-tag` | Images use a specific tag, not `:latest` |
| `require-labels` | Pods have the `app.kubernetes.io/name` label |

### Checking Policy Reports

To see which workloads violate policies:

```bash
kubectl get policyreport -A
```

For detailed violation messages:

```bash
kubectl get policyreport -A -o yaml | grep -A 5 "result: fail"
```

### Moving to Enforce Mode

Once all violations are resolved, change `validationFailureAction` from `Audit` to `Enforce` in the policy YAML files under `k8s/components/kyverno-policies/`. Enforced policies will reject non-compliant workloads at admission time.

!!! warning "Test Before Enforcing"
    Switching to Enforce mode will block any pod that violates the policy. Review all audit violations first to avoid breaking running workloads during the next rollout.

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
