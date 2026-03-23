# Network Policies

CiliumNetworkPolicies provide namespace-level ingress isolation. Each application namespace has a default-deny rule for external traffic, with explicit allow rules for legitimate communication paths.

## Policy Overview

| Namespace | Policies | Allows Ingress From |
|-----------|----------|---------------------|
| `arr` | 4 | ingress-nginx, arr (internal), monitoring |
| `auth` | 4 | ingress-nginx, auth (internal), monitoring |
| `monitoring` | 4 | ingress-nginx, monitoring (internal), cluster-wide (Prometheus) |
| `backups` | 3 | backups (internal), monitoring |

## Design

Each namespace follows the same pattern:

1. **Default deny from world** -- blocks unsolicited external ingress.
2. **Allow from ingress-nginx** -- permits traffic routed through the nginx ingress controller (web UIs).
3. **Allow internal** -- permits pod-to-pod communication within the same namespace.
4. **Allow from monitoring** -- permits Prometheus to scrape metrics endpoints.

The `monitoring` namespace has an additional rule allowing cluster-wide ingress to Prometheus, which is necessary for Grafana queries and federation.

The `backups` namespace does not need ingress-nginx access because MinIO's console ingress is disabled. Velero communicates with MinIO via internal service URLs.

### What Is Not Restricted

- **Egress** is unrestricted across all namespaces. Pods can reach external services (NFS, DNS, VPN endpoints, Slack webhooks) without explicit egress rules.
- **kube-system** and **ingress-nginx** namespaces have no policies applied, as restricting them could break cluster-wide functionality.

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
