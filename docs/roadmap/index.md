# Roadmap

A plan for evolving the homelab as a household media platform and an infrastructure learning environment. The phases group related work; they are not a required execution order. Choose projects by their actual dependencies and available capacity.

See the [hardware inventory](../reference/hardware.md), [network infrastructure](../architecture/network-infrastructure.md), and [architecture overview](../architecture/overview.md) for the current setup.

## Start Here

**Next software project: finish clean lab bootstrap.** The [isolated lab](../runbooks/restore-lab.md#combined-machine-and-application-recovery-drill) now has a verified fresh-machine and offsite application-recovery path. Rebuild it from verified Packer template `9011`, then bootstrap ArgoCD and its Applications without preexisting CRDs or Secrets. Use the remaining [recovery checks](phase-1-foundations.md#12-verify-recovery); the lab can later become the persistent [staging cluster](phase-6-platform-engineering.md#61-staging-cluster).

**Next, upgrade Kubernetes to a supported release.** Use that lab to rehearse each minor-version step, check Cilium/chart compatibility and prove a fresh node join before upgrading the household cluster. Follow [Phase 2.1](phase-2-kubernetes-hardening.md#21-upgrade-the-unsupported-platform).

**Hardware is a separate workstream.** The [NAS mirror](phase-1-foundations.md#11-add-nas-drive-redundancy), [10G links](phase-3-network.md#31-enable-10g-networking) and [second MS-01](phase-4-compute-and-storage.md#41-add-a-second-compute-host) remain planned purchases. None is a prerequisite for starting the software lab on available capacity. Keep their design and migration tasks in their respective phases and pick them up when the hardware is available.

The roadmap contains remaining work. Remove completed tasks; keep enduring operational details in the application docs and runbooks, and completion history in Git. Restore, upgrade and user-facing acceptance checks stay open until demonstrated.

## Phases

| Phase | Focus | Status |
|---|---|---|
| [1 — Foundations](phase-1-foundations.md) | UPS, NAS drive redundancy, offsite backups, etcd snapshots and recovery | In progress; backup mechanisms implemented, mirror and restore checks remain |
| [2 — Kubernetes Hardening](phase-2-kubernetes-hardening.md) | Supported upgrades, policy coverage, quotas, certificate alerts and egress controls | In progress; enforcement and alerting implemented |
| [3 — Network](phase-3-network.md) | 10G switch and DAC links, management VLAN, WireGuard, DNS automation and external access | In progress; WireGuard/Teleport implemented, 10G upgrade planned |
| [4 — Compute & Storage](phase-4-compute-and-storage.md) | Second MS-01, three control planes, Vault Raft and NAS expansion | Planned |
| [5 — Observability](phase-5-observability.md) | Distributed tracing, dashboards as code, SLO alerting and synthetic monitoring | In progress; dashboards and Blackbox probes implemented |
| [6 — Platform Engineering](phase-6-platform-engineering.md) | Staging cluster, Falco, chaos testing, supply-chain verification and scoped automation | In progress; CI validation and scoped OpenClaw configuration implemented |
| [7 — Long-Term Vision](phase-7-long-term-vision.md) | Third host, Crossplane, multi-cluster management, dedicated GPU and full 10G fabric | Planned |
| [8 — Configuration as Code](phase-8-configuration-as-code.md) | Media application configuration, Authentik blueprints and media-platform improvements | In progress; operators and blueprints implemented, fresh-install checks remain |

## Assessment

The [assessment](assessment.md) is the current inventory of capabilities, constraints and remaining work. Each finding points to its implementation phase; completed fixes belong in the code and runbooks, with their history in Git.

## Principles

1. **Protect data first.** UPS protection, redundant NAS drives and offsite backups cover different failures. Keep restore testing alongside those improvements.
2. **Reduce single points of failure.** Add the planned storage redundancy and independent compute capacity. Distinguish VM redundancy from physical-host redundancy when designing control-plane and Vault placement.
3. **Enforce incrementally.** Existing admission policies are enforced. Validate coverage and workload compatibility as new policies and resource budgets are introduced.
4. **Prefer maintainable solutions.** Build on the existing Proxmox, NFS, GitOps and AWS backup setup when it meets the requirement.
5. **Hardware unlocks capabilities.** A second host enables staging, workload distribution and maintenance flexibility; 10G improves the storage path. Three quorum members across two physical hosts still cannot survive either host failing.
6. **Document architecture decisions.** ADRs record a chosen architecture, its alternatives and consequences. Task status and changes to the plan belong in the roadmap.
7. **Keep learning as a goal.** Tracing, SLOs, chaos engineering, runtime security and supply-chain verification are worthwhile projects at homelab scale.
