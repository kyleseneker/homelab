# ADR-023: Scoped Autonomous Remediation for OpenClaw

## Status

Accepted

## Context

OpenClaw diagnoses cluster problems and responds to Slack messages and application alerts. Autonomous recovery is useful for routine failures, but unrestricted pod exec or workload-template mutation can access credentials and execute code under other workload identities. The permitted recovery actions need an access boundary enforced by Kubernetes.

## Decision

Give OpenClaw explicit cluster read permissions for diagnosis, without Secret reads or pod exec. Limit Kubernetes writes to `deployments/scale` for `homepage` and `arr-flaresolverr` in the `arr` namespace, using a namespaced Role with `resourceNames`.

The intended remediation is restoring those companion workloads to their declared replica counts. GitOps remains the desired-state owner. Node changes, arbitrary workload-template changes and deletion are outside OpenClaw's Kubernetes permissions.

Require Slack pairing and authenticated webhooks for incoming requests. Treat write-capable media API credentials as a separate access boundary from Kubernetes RBAC.

## Alternatives Considered

- **Read-only diagnosis**: Minimizes write authority but requires an operator for every recovery action.
- **Broad workload mutation and pod exec**: Supports more operations but also permits arbitrary code execution and access to workload credentials.
- **Namespace-wide write access**: Limits the namespace but still allows mutations to stateful media workloads beyond the intended recovery actions.

## Rationale

- **Retained autonomy**: Routine scaling recovery can run without manual intervention.
- **Enforced scope**: Kubernetes limits both the target objects and the writable subresource; operating instructions describe the desired behavior within that boundary.
- **Preserved configuration ownership**: Temporary remediation does not give the agent authority to rewrite workload specifications managed in Git.

## Consequences

- OpenClaw cannot restart arbitrary workloads, repair nodes or perform cluster-wide cleanup. Additional operations need a deliberately scoped implementation.
- RBAC restricts the scale target but does not bound the numeric replica count. Resource budgets and operating instructions still matter.
- Kubernetes RBAC does not restrict actions available through media API keys; their consumers and write permissions require separate control.
