# ADR-003: CiliumNetworkPolicy for Namespace Isolation

## Status

Accepted

## Context

With multiple applications sharing a cluster, a compromised or misconfigured pod could communicate with any other pod by default. The cluster needs network segmentation to enforce least-privilege communication between namespaces and to the outside world.

## Decision

Use CiliumNetworkPolicy resources to define permitted ingress and egress for selected pods. Policies select workloads by namespace and component labels. Once a policy enables enforcement in a direction, traffic in that direction must match an allow rule.

Each namespace's baseline, the rules every pod in it shares, lives in the `network-policies` directory with one file per namespace. Rules for a single workload live in a `networkpolicy.yml` beside that workload's manifests and ship in its Argo CD application, so a workload and the traffic it needs change in one commit. Addresses outside the cluster are named once, as `CiliumCIDRGroup` objects, and policies refer to them by name.

## Alternatives Considered

- **Standard Kubernetes NetworkPolicy**: Portable across CNIs and supports isolation of selected pods, but lacks Cilium's entity-based selectors (`world`, `cluster`, `ingress`, `host`, `kube-apiserver`) and FQDN-based egress rules.
- **Calico NetworkPolicy**: Rich policy model comparable to Cilium's, but would require running Calico alongside or instead of Cilium (ADR-002). Running two CNI policy engines adds complexity.
- **No network policies**: Simpler to operate but provides no blast-radius containment. Any pod can reach any other pod and any external endpoint.

## Rationale

- **Entity-based selectors**: Cilium entities like `ingress`, `cluster`, `kube-apiserver`, and `world` express intent more clearly than raw IP ranges or namespace label selectors. For example, allowing a metrics collector to scrape a namespace is `fromEndpoints: [{matchLabels: {kubernetes.io/metadata.name: monitoring}}]` rather than maintaining IP lists.
- **Implicit egress deny**: Defining any egress rule on a CiliumNetworkPolicy automatically denies all other egress for matched pods. This avoids the error-prone pattern of maintaining separate default-deny policies that must stay in sync.
- **Per-component egress rules**: Pod-level label selectors allow fine-grained egress control within a namespace, giving each component only the external access it needs rather than granting blanket egress to the entire namespace.
- **Consistent pattern**: Namespace policies share a structure of explicit ingress and egress rules, with component-specific exceptions expressed through pod labels.
- **Common rules across namespaces**: DNS egress (kube-dns on port 53) and storage access appear in every namespace baseline that needs them, following a repeatable template.
- **Ownership**: a workload's exceptions sit next to its chart values, where a change to its ports or destinations is made. Deleting an app removes its policy with it, so no orphaned rules accumulate in a central file.

## Policy Posture by Namespace Category

- **User-facing apps**: Allow ingress from `ingress` entity (Cilium Gateway), intra-namespace, and metrics collection. Egress to DNS, storage, and service-specific destinations.
- **Infrastructure services**: Allow ingress from `cluster`, `kube-apiserver`, and `host` entities for webhook and API calls. No gateway ingress. Minimal egress.
- **kube-system**: No policies applied. Restricting core cluster components risks breaking fundamental cluster functionality.

## Consequences

- Every new namespace must have a baseline file. Without one, the namespace has no restrictions. A workload that needs more than its namespace baseline brings its own `networkpolicy.yml`.
- Debugging connectivity issues requires familiarity with Cilium's `hubble observe` tooling to trace dropped packets and identify which policy is blocking traffic.
- Changing an external address means editing its `CiliumCIDRGroup`. `except` lists accept only literal CIDRs, so exclusions still spell out their ranges.
- Overly restrictive policies can silently break functionality (e.g., a missing scrape exception prevents metrics collection from a new namespace). Policy changes should be tested by verifying service connectivity after deployment.
