# Cilium Gateway API

Cilium serves as both the CNI and the Gateway API controller, providing hostname-based HTTPS routing to backend services via HTTPRoute resources.

## Details

| Field | Value |
|-------|-------|
| Gateway Class | `cilium` |
| Gateway Name | `homelab-gateway` |
| Namespace | `default` |
| Listeners | HTTPS (443), HTTP (80, redirect only) |
| TLS | Wildcard cert for `*.homelab.local` via cert-manager |
| IP Pool | `192.168.10.200-250` (CiliumLoadBalancerIPPool) |

## Key Configuration

### Gateway

The `homelab-gateway` resource defines two listeners:

- **HTTPS (443):** Terminates TLS for `*.homelab.local` using a cert-manager-issued certificate. Allows routes from all namespaces.
- **HTTP (80):** Accepts traffic for `*.homelab.local` and redirects to HTTPS.

### L2 Announcements

Cilium's L2 announcement policy advertises LoadBalancer IPs via ARP on the local network, replacing MetalLB:

- **CiliumLoadBalancerIPPool (`homelab-pool`):** Allocates IPs from `192.168.10.200-250`.
- **CiliumL2AnnouncementPolicy (`homelab-l2`):** Enables ARP-based IP advertisement for all LoadBalancer services.

### Gateway API CRDs

The Gateway API CRDs are installed from upstream manifests at sync wave -3 via the `gateway-api` ArgoCD Application in `k8s/components/gateway-api/`. This ensures CRDs exist before the Gateway resource is created.

## Cluster Integration

All applications define HTTPRoute resources that bind to the `homelab-gateway`:

```yaml
route:
  main:
    enabled: true
    kind: HTTPRoute
    parentRefs:
      - group: gateway.networking.k8s.io
        kind: Gateway
        name: homelab-gateway
        namespace: default
        sectionName: https
    hostnames:
      - <app>.homelab.local
    rules:
      - matches:
          - path:
              type: PathPrefix
              value: /
        backendRefs:
          - name: <service-name>
            port: <port>
```

The gateway deploys with the core infrastructure. The Gateway API CRDs install at sync wave -3, and the gateway configuration (Gateway + L2 pool) deploys alongside other infrastructure components.

## Upstream Documentation

- Gateway API: <https://gateway-api.sigs.k8s.io>
- Cilium Gateway API: <https://docs.cilium.io/en/stable/network/servicemesh/gateway-api/>
