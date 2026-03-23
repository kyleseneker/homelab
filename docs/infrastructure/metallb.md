# MetalLB

MetalLB provides a bare-metal LoadBalancer implementation for the cluster, allowing services of type `LoadBalancer` to receive LAN-routable IP addresses without a cloud provider.

## Details

| Field | Value |
|-------|-------|
| Chart | `metallb` |
| Repository | <https://metallb.github.io/metallb> |
| Version | 0.14.9 |
| Namespace | `metallb-system` (CreateNamespace=true, ServerSideApply=true) |
| Sync Wave | -3 |

## Key Configuration

MetalLB is deployed in two stages:

### Stage 1: MetalLB Controller (sync wave -3)

The Helm chart installs the MetalLB speaker and controller. Server-Side Apply is enabled to handle CRD ownership cleanly.

### Stage 2: MetalLB Config (sync wave -2)

A separate ArgoCD Application (`metallb-config`) deploys the address pool and advertisement resources as plain manifests from `k8s/components/metallb-config/` in the Git repository. This two-stage approach is necessary because the MetalLB CRDs must exist before the custom resources can be applied.

- **IPAddressPool**: `homelab-pool` allocates addresses from `192.168.10.200-250`.
- **L2Advertisement**: `homelab-l2` advertises allocated IPs via Layer 2 (ARP), making them reachable on the local network segment.

The config application uses a retry policy of limit 30 with exponential backoff from 10 seconds to 5 minutes to handle the CRD readiness race.

## Cluster Integration

MetalLB is the first networking primitive in the stack. The ingress-nginx controller and any other `LoadBalancer` services depend on MetalLB to assign external IPs. It deploys at sync wave -3 (with config at -2) so that IP allocation is available before ingress controllers start at wave -1.

## Upstream Documentation

<https://metallb.io>
