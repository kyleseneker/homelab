# ADR-014: Kyverno for Policy Enforcement

## Status

Accepted

## Context

The cluster needs guardrails to enforce security and operational standards across all workloads: image tag hygiene, resource limits, non-root execution, read-only filesystems, and standard labeling. These should be enforced or audited consistently without relying on manual review of every manifest.

## Decision

Use Kyverno as the Kubernetes policy engine. All five ClusterPolicies run in Enforce mode, blocking non-compliant pods at admission. Namespaces with workloads that cannot conform (linuxserver root images, Velero dynamic jobs, GPU operators) are excluded per-policy rather than left in audit mode.

## Alternatives Considered

- **OPA / Gatekeeper**: The original Kubernetes policy engine. Policies are written in Rego, a purpose-built query language. Powerful but steep learning curve — Rego is unfamiliar to most Kubernetes operators and harder to review in pull requests.
- **Kubewarden**: Policies as WebAssembly modules. Interesting technology but smaller ecosystem and community compared to Kyverno. Fewer pre-built policies available.
- **Pod Security Standards (PSS) only**: Built into Kubernetes via namespace labels. Limited to three fixed profiles (privileged, baseline, restricted) with no custom rules. Cannot enforce image tag policies, label requirements, or resource limits.
- **No policy engine**: Rely on code review and convention. Works until it doesn't — one missed `:latest` tag or missing resource limit can cause production issues.

## Rationale

- **Kubernetes-native policies**: Kyverno policies are written as Kubernetes YAML resources, not a separate language. ClusterPolicy manifests are readable by anyone familiar with Kubernetes and reviewable in the same PR workflow as application manifests.
- **Full enforcement with targeted exclusions**: All policies enforce at admission. Workloads that cannot conform (linuxserver root images, Velero dynamic jobs, GPU device plugins) are excluded by namespace rather than leaving policies in audit mode cluster-wide.
- **Namespace exclusions**: System namespaces (kube-system, kyverno, argocd, metallb-system, cilium-test) are excluded from all policies. Application namespaces with legitimate non-compliance (arr, auth, backups, monitoring, nfs-provisioner, intel-gpu-operator) are excluded only from the specific policies they cannot satisfy.
- **Background scanning**: All policies run with `background: true`, scanning existing resources on schedule — not just at admission time. This catches drift and pre-existing violations.

## Consequences

- Kyverno's admission webhook adds latency to all pod creation requests. With a single replica, webhook unavailability could block deployments. A PDB or replica increase may be warranted as the cluster grows.
- Namespace exclusion lists must be maintained as new infrastructure namespaces are added. A missed exclusion could block critical system pods.
- Excluded namespaces should be revisited periodically -- if upstream images add non-root support or workloads gain resource limits, exclusions can be removed to tighten coverage.
