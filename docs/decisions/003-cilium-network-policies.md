# ADR-003: CiliumNetworkPolicy for Namespace Isolation

## Status

Accepted

## Context

With multiple applications sharing a cluster, a compromised or misconfigured pod could communicate with any other pod by default. The cluster needs network segmentation to enforce least-privilege communication between namespaces and to the outside world.

## Decision

Use CiliumNetworkPolicy resources with a default-deny ingress posture per namespace. Each namespace declares explicit allow rules for the traffic it needs. Egress is controlled via Cilium's implicit deny model: once any egress rule is defined for a namespace, all other egress is denied without requiring an explicit deny rule.

Policies are managed as a single git directory with one YAML file per namespace.

## Alternatives Considered

- **Standard Kubernetes NetworkPolicy**: Portable across CNIs but limited expressiveness. No support for entity-based selectors (`world`, `cluster`, `ingress`, `host`, `kube-apiserver`), no FQDN-based egress rules, and no implicit deny model — requires explicit default-deny policies per namespace.
- **Calico NetworkPolicy**: Rich policy model comparable to Cilium's, but would require running Calico alongside or instead of Cilium (ADR-002). Running two CNI policy engines adds complexity.
- **No network policies**: Simpler to operate but provides no blast-radius containment. Any pod can reach any other pod and any external endpoint.

## Rationale

- **Entity-based selectors**: Cilium entities like `ingress`, `cluster`, `kube-apiserver`, and `world` express intent more clearly than raw IP ranges or namespace label selectors. For example, allowing a metrics collector to scrape a namespace is `fromEndpoints: [{matchLabels: {kubernetes.io/metadata.name: monitoring}}]` rather than maintaining IP lists.
- **Implicit egress deny**: Defining any egress rule on a CiliumNetworkPolicy automatically denies all other egress for matched pods. This avoids the error-prone pattern of maintaining separate default-deny policies that must stay in sync.
- **Per-component egress rules**: Pod-level label selectors allow fine-grained egress control within a namespace, giving each component only the external access it needs rather than granting blanket egress to the entire namespace.
- **Consistent pattern**: Every namespace follows the same structure — default deny ingress from `world`, then explicit allow rules for gateway access, intra-namespace communication, and any namespace-specific integrations.
- **Common rules across namespaces**: DNS egress (kube-dns on port 53) and storage access appear in every namespace that needs them, following a repeatable template.

## Policy Posture by Namespace Category

- **User-facing apps**: Allow ingress from `ingress` entity (Cilium Gateway), intra-namespace, and metrics collection. Egress to DNS, storage, and service-specific destinations.
- **Infrastructure services**: Allow ingress from `cluster`, `kube-apiserver`, and `host` entities for webhook and API calls. No gateway ingress. Minimal egress.
- **kube-system**: No policies applied. Restricting core cluster components risks breaking fundamental cluster functionality.

## Consequences

- Every new namespace must have a corresponding network policy file. Without one, the namespace has no restrictions.
- Debugging connectivity issues requires familiarity with Cilium's `hubble observe` tooling to trace dropped packets and identify which policy is blocking traffic.
- Static IPs (e.g., storage backend addresses) are hardcoded in egress rules across multiple namespace policies. Changing an address requires updating all policy files.
- Overly restrictive policies can silently break functionality (e.g., a missing scrape exception prevents metrics collection from a new namespace). Policy changes should be tested by verifying service connectivity after deployment.
