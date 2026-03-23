# ingress-nginx

ingress-nginx is the cluster's ingress controller, providing hostname-based HTTP/HTTPS routing to backend services.

## Details

| Field | Value |
|-------|-------|
| Chart | `ingress-nginx` |
| Repository | <https://kubernetes.github.io/ingress-nginx> |
| Version | 4.12.0 |
| Namespace | `ingress-nginx` (CreateNamespace=true, ServerSideApply=true) |
| Sync Wave | -1 |

## Key Configuration

- **Controller mode**: Runs as a `DaemonSet` so every schedulable node handles ingress traffic.
- **Service type**: `LoadBalancer`. MetalLB assigns an external IP from the homelab address pool, making the controller reachable on the LAN.
- **Server-Side Apply**: Enabled to avoid field-manager conflicts with the large ingress-nginx CRD surface area.

## Cluster Integration

All applications define their Ingress resources with:

```yaml
ingressClassName: nginx
```

The controller terminates TLS using certificates issued by cert-manager and forwards traffic to the appropriate ClusterIP service based on hostname rules.

ingress-nginx deploys at sync wave -1 because it depends on:

- **MetalLB** (wave -3 / -2) to assign a LoadBalancer IP.
- **cert-manager** (wave -3) to issue TLS certificates referenced by Ingress resources.

## Upstream Documentation

<https://kubernetes.github.io/ingress-nginx>
