# ADR-001: Cilium as CNI and Gateway Controller

## Status

Accepted

## Context

The cluster needs a Container Network Interface (CNI) plugin for pod networking, a mechanism for exposing services externally (ingress/gateway), and network policy enforcement. These are typically served by separate components (e.g., Flannel + ingress-nginx + NetworkPolicy controller), but Cilium can consolidate all three.

## Decision

Use Cilium as the CNI with kube-proxy replacement, Gateway API support, and L2 announcements enabled. This replaces what would otherwise require separate installations of Flannel/Calico (CNI), ingress-nginx (ingress), MetalLB (LoadBalancer IPs), and a NetworkPolicy controller.

## Alternatives Considered

- **Flannel + ingress-nginx + MetalLB**: The original stack. Simpler individual components but three separate installations, three upgrade cycles, and limited network policy support. The cluster previously used this combination before migrating.
- **Calico**: Strong network policy support but no Gateway API or L2 announcement features, requiring additional components for ingress and LoadBalancer IPs.
- **Traefik**: Good ingress controller but doesn't solve CNI or LoadBalancer IP allocation.

## Rationale

- **Consolidation**: One component replaces three (CNI + gateway + L2), reducing operational surface area.
- **Gateway API**: The Kubernetes-standard successor to Ingress. HTTPRoute resources are more expressive than Ingress and avoid annotation-driven configuration.
- **kube-proxy replacement**: eBPF-based packet processing eliminates iptables overhead.
- **L2 announcements**: Native ARP-based IP advertisement removes the MetalLB dependency entirely.
- **CiliumNetworkPolicy**: Richer policy model than standard Kubernetes NetworkPolicy (e.g., FQDN-based egress rules, implicit deny behavior).

## Consequences

- Cilium is a larger, more complex component than Flannel. Upgrades require more care.
- Gateway API is newer than Ingress; some Helm charts still default to Ingress resource templates, requiring manual HTTPRoute configuration.
- Debugging network issues requires familiarity with Cilium's `hubble` observability tooling rather than standard iptables debugging.
