# Roadmap

A phased plan for evolving the homelab into a more resilient, production-grade platform. Each phase builds on the previous one -- earlier phases address foundational risks, later phases add capabilities.

For current infrastructure details, see [Hardware Inventory](../reference/hardware.md), [Network Infrastructure](../architecture/network-infrastructure.md), and [Architecture Overview](../architecture/overview.md).

## Phases

| Phase | Focus | Status |
|-------|-------|--------|
| [1 -- Foundations](phase-1-foundations.md) | ~~UPS~~, NAS redundancy, ~~offsite backups~~, ~~etcd snapshots~~ | In progress |
| [2 -- Kubernetes Hardening](phase-2-kubernetes-hardening.md) | Policy enforcement, resource quotas, registry allowlist, cert-manager alerting, egress filtering | In progress |
| [3 -- Network](phase-3-network.md) | 10G, management VLAN, WireGuard VPN, DNS automation, external access | Not started |
| [4 -- Compute & Storage](phase-4-compute-and-storage.md) | Second host, HA control plane, Vault HA, NAS expansion | Not started |
| [5 -- Observability](phase-5-observability.md) | Distributed tracing, dashboards-as-code, SLO alerting, synthetic monitoring | Not started |
| [6 -- Platform Engineering](phase-6-platform-engineering.md) | Staging cluster, Falco, chaos engineering, supply chain security, vPro AMT | Not started |
| [7 -- Long-Term Vision](phase-7-long-term-vision.md) | Third host, Crossplane, multi-cluster GitOps, dedicated GPU, full 10G | Not started |

## Assessment

See [Assessment](assessment.md) for the full analysis of current strengths and identified gaps that drive this roadmap.

## Principles

1. **Protect data before optimizing performance.** UPS, drive redundancy, and offsite backups come before 10G networking or HA control planes.
2. **Eliminate SPOFs in order of blast radius.** NAS (all data) > compute host (all VMs) > control plane (cluster management) > individual services.
3. **Graduate from audit to enforce.** Policies that only report are policies that get ignored.
4. **Prefer boring solutions.** Backblaze B2 over a self-hosted S3 cluster. ResourceQuotas over custom admission webhooks. WireGuard over a bespoke proxy chain.
5. **Hardware purchases should unlock capabilities, not just add capacity.** A second host unlocks HA, live migration, and rolling upgrades. 10G unlocks the SFP+ ports already in the MS-01.
6. **Every significant change gets an ADR.** The documentation standard is a strength worth maintaining.
7. **Use the homelab to learn, not just host.** Tracing, SLOs, chaos engineering, Falco, and supply chain security are career-relevant skills worth building even when a 3-node cluster doesn't strictly require them.
