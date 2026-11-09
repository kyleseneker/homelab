# Cilium Gateway API

Cilium serves as both the CNI and the Gateway API controller, providing hostname-based HTTPS routing to backend services via HTTPRoute resources.

## Details

| Field | Value |
|-------|-------|
| Gateway Class | `cilium` |
| Gateway Name | `homelab-gateway` |
| Namespace | `default` |
| Listeners | HTTPS (443), HTTP (80, redirect only), each for `*.home.seneker.io` and `home.seneker.io` |
| TLS | `home-gateway-tls` for `*.home.seneker.io` and `home.seneker.io`, from Let's Encrypt via cert-manager |
| IP Pool | `192.168.10.200-250` (CiliumLoadBalancerIPPool) |

## Key Configuration

### Gateway

The `homelab-gateway` resource defines four listeners. A wildcard listener does not match the bare `home.seneker.io`, which serves Homepage, so it has its own pair:

- **`https-home` (443):** Terminates TLS for `*.home.seneker.io` with `home-gateway-tls`. Allows routes from all namespaces.
- **`https-home-root` (443):** Terminates TLS for `home.seneker.io` with the same certificate. Allows routes from all namespaces.
- **`http-home` and `http-home-root` (80):** Accept traffic for the same names and redirect it to HTTPS (`gateway/http-redirect.yml`).

The Gateway does not currently request a fixed address. Its live address, 192.168.10.201, is what the UniFi wildcard record `*.home.seneker.io` and the bare `home.seneker.io` record point at. Recreating the Gateway can assign a different IP from the pool and break every service name until those two records are updated; pinning it with `spec.addresses` is tracked in [Phase 3](../roadmap/phase-3-network.md#33-pin-the-gateway-address).

### L2 Announcements

Cilium's L2 announcement policy advertises LoadBalancer IPs via ARP on the local network, replacing MetalLB:

- **CiliumLoadBalancerIPPool (`homelab-pool`):** Allocates IPs from `192.168.10.200-250`.
- **CiliumL2AnnouncementPolicy (`homelab-l2`):** Enables ARP-based IP advertisement for all LoadBalancer services.

### Gateway API CRDs

The Gateway API CRDs are installed from upstream manifests via the `gateway-api` ArgoCD Application in `k8s/components/gateway-api/`. They must exist before the Gateway resource is created; if the Gateway syncs first it fails and ArgoCD retries until the CRDs land.

The directory vendors the unmodified standard-channel files for the resources Cilium 1.20 requires: GatewayClass, Gateway, HTTPRoute, GRPCRoute, ReferenceGrant, TLSRoute and BackendTLSPolicy. Do not run a Cilium 1.19 operator against this set: it treats the TLSRoute CRD's unserved `v1alpha2` as installed. The [Cilium upgrade procedure](../runbooks/upgrading-kubernetes.md#upgrade-cilium) covers rollback. The directory omits `safe-upgrades.gateway.networking.k8s.io`, the ValidatingAdmissionPolicy that upstream bundles from v1.5. That policy blocks CRD downgrades below v1.5, and the bootstrap's `kubectl wait --for=condition=Established` over this directory cannot wait on a non-CRD object. Upgrade the CRDs one minor at a time and keep every version the running Cilium release requires.

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
        sectionName: https-home
    hostnames:
      - <app>.home.seneker.io
    rules:
      - matches:
          - path:
              type: PathPrefix
              value: /
        backendRefs:
          - name: <service-name>
            port: <port>
```

The gateway deploys with the core infrastructure. The CRDs come from the `gateway-api` Application; the gateway configuration (Gateway + L2 pool) is a separate `gateway` Application.

## Upstream Documentation

- Gateway API: <https://gateway-api.sigs.k8s.io>
- Cilium Gateway API: <https://docs.cilium.io/en/stable/network/servicemesh/gateway-api/>
