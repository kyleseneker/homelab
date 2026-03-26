# Network Policies

CiliumNetworkPolicies provide namespace-level ingress isolation. Each application namespace has a default-deny rule for external traffic, with explicit allow rules for legitimate communication paths.

## Policy Overview

| Namespace | Policies | Allows Ingress From |
|-----------|----------|---------------------|
| `arr` | 4 | gateway (ingress), arr (internal), monitoring, openclaw |
| `auth` | 4 | gateway (ingress), auth (internal), monitoring, cluster-wide |
| `monitoring` | 4 | gateway (ingress), monitoring (internal), cluster-wide (Prometheus) |
| `backups` | 3 | backups (internal), monitoring |

## Design

Each namespace follows the same pattern:

1. **Default deny from world** -- blocks unsolicited external ingress.
2. **Allow from gateway (ingress entities)** -- permits traffic routed through the Cilium Gateway (web UIs).
3. **Allow internal** -- permits pod-to-pod communication within the same namespace.
4. **Allow from monitoring** -- permits Prometheus to scrape metrics endpoints.

The `monitoring` namespace has an additional rule allowing cluster-wide ingress to Prometheus, which is necessary for Grafana queries and federation.

The `backups` namespace does not need gateway access because MinIO is accessed only via internal service URLs.

The `openclaw` namespace has granular egress rules: the ops agent gets egress to the K8s API, GitHub, Slack, Anthropic, and media claw; the media agent gets egress to the arr namespace and external HTTPS only.

### What Is Not Restricted

- **kube-system** namespace has no policies applied, as restricting it could break cluster-wide functionality.

## Troubleshooting

If a service becomes unreachable after policy deployment, check whether the traffic source namespace is allowed:

```bash
kubectl get ciliumnetworkpolicies -n <namespace>
```

To temporarily remove a policy blocking traffic:

```bash
kubectl delete ciliumnetworkpolicy <policy-name> -n <namespace>
```

Since policies are managed by ArgoCD, deleted policies will be re-created on the next sync. To permanently remove a policy, delete the corresponding YAML from `k8s/clusters/homelabk8s01/infrastructure/network-policies/`.
