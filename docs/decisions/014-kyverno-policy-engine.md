# ADR-014: Kyverno for Policy Enforcement

## Status

Accepted

## Context

The cluster needs guardrails to enforce security and operational standards across all workloads: image tag hygiene, resource limits, non-root execution, read-only filesystems, and standard labeling. These should be enforced or audited consistently without relying on manual review of every manifest.

## Decision

Use Kyverno as the Kubernetes policy engine with a mix of enforced and audit-only ClusterPolicies. Two policies block violations at admission (disallow-latest-tag, require-labels). Three policies run in audit mode and report violations without blocking (require-resource-limits, require-run-as-nonroot, require-readonly-rootfs).

## Alternatives Considered

- **OPA / Gatekeeper**: The original Kubernetes policy engine. Policies are written in Rego, a purpose-built query language. Powerful but steep learning curve — Rego is unfamiliar to most Kubernetes operators and harder to review in pull requests.
- **Kubewarden**: Policies as WebAssembly modules. Interesting technology but smaller ecosystem and community compared to Kyverno. Fewer pre-built policies available.
- **Pod Security Standards (PSS) only**: Built into Kubernetes via namespace labels. Limited to three fixed profiles (privileged, baseline, restricted) with no custom rules. Cannot enforce image tag policies, label requirements, or resource limits.
- **No policy engine**: Rely on code review and convention. Works until it doesn't — one missed `:latest` tag or missing resource limit can cause production issues.

## Rationale

- **Kubernetes-native policies**: Kyverno policies are written as Kubernetes YAML resources, not a separate language. ClusterPolicy manifests are readable by anyone familiar with Kubernetes and reviewable in the same PR workflow as application manifests.
- **Graduated enforcement**: Audit mode allows introducing policies without breaking existing workloads. Violations are reported via PolicyReport resources, providing visibility into non-compliance before enforcement begins.
- **Selective enforcement**: `disallow-latest-tag` and `require-labels` are enforced because they catch common mistakes with low false-positive risk. Security policies (non-root, readonly-rootfs, resource-limits) are audit-only because some workloads (linuxserver images, GPU operators) have legitimate exceptions that need resolution before enforcement.
- **Namespace exclusions**: System namespaces (kube-system, kyverno, argocd) and specific workloads (cilium-test) are excluded to avoid blocking cluster-critical components that don't conform to application-level policies.
- **Background scanning**: All policies run with `background: true`, scanning existing resources on schedule — not just at admission time. This catches drift and pre-existing violations.

## Consequences

- Kyverno's admission webhook adds latency to all pod creation requests. With a single replica, webhook unavailability could block deployments. A PDB or replica increase may be warranted as the cluster grows.
- Audit-mode policies generate PolicyReports but do not prevent non-compliant resources. Compliance depends on actively reviewing reports and remediating violations.
- Namespace exclusion lists must be maintained as new infrastructure namespaces are added. A missed exclusion could block critical system pods.
- Moving audit policies to enforce mode requires first resolving all existing violations, which may involve upstream image changes or security context workarounds.
