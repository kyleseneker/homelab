# Phase 6 -- Platform Engineering

**Status:** Not started

**Goal:** Build the capabilities that take the homelab from "well-run cluster" to a platform engineering practice.

**Addresses:** [P6](assessment.md#physical-layer) (no remote management), [K12, K13](assessment.md#kubernetes--software-layer) (no chaos testing, no supply chain verification)

---

## 6.1 Staging Cluster

- [ ] Provision a second Kubernetes cluster (1 CP + 1 worker) on the second host
- [ ] Configure ArgoCD ApplicationSet with a separate overlay or branch for staging
- [ ] Establish a promotion workflow: staging &rarr; production
- [ ] Use staging for all Kubernetes upgrades and Cilium bumps before production
- [ ] Write an ADR

| | |
|---|---|
| **Why** | Every infrastructure change is currently tested directly in production. A staging cluster allows validating changes safely and practicing DR procedures without risk. |
| **Prerequisites** | Second compute host (Phase 4.1). |

## 6.2 Runtime Security with Falco

- [ ] Deploy Falco as a DaemonSet
- [ ] Deploy Falcosidekick to route alerts to Alertmanager
- [ ] Tune default rules to reduce noise for homelab workloads
- [ ] Verify alerts appear in Slack via existing Alertmanager pipeline
- [ ] Write an ADR

| | |
|---|---|
| **Why** | Current security controls operate at admission time (Kyverno) and network time (Cilium). Nothing monitors what happens inside a running container. Falco detects: shell spawned in container, sensitive file read, unexpected network connection, privilege escalation. |

## 6.3 Chaos Engineering

- [ ] Deploy Litmus or Chaos Mesh
- [ ] Create experiments: pod kills, node cordons, NFS interruptions, DNS failures
- [ ] Schedule weekly experiments during low-traffic hours
- [ ] Document results and any gaps discovered
- [ ] Write an ADR

| | |
|---|---|
| **Why** | DR runbooks exist but are never automatically validated. Chaos experiments prove the cluster recovers as documented and expose gaps before real incidents find them. |
| **Cadence** | Start with pod-kill experiments. Escalate to node-drain and network-partition tests. |

## 6.4 Supply Chain Security

- [ ] Add a Kyverno policy requiring cosign signature verification for deployed images
- [ ] Optionally deploy Harbor as a pull-through registry cache with vulnerability scanning
- [ ] Write an ADR

| | |
|---|---|
| **Why** | Renovate pins digests (preventing tag mutation), but no verification that images were built by trusted parties. cosign ensures images are signed by their maintainers. Harbor adds scanning and caching. |

## 6.5 Enable Intel vPro AMT

- [ ] Configure Intel AMT on the MS-01 for out-of-band management (remote KVM, power control)
- [ ] Place AMT on the Management VLAN (Phase 3.2)
- [ ] Test remote power cycle and console access
- [ ] Configure on second host (Phase 4.1) when available

| | |
|---|---|
| **Why** | A hung Proxmox host requires physical access. AMT provides IPMI-like capabilities over the network. |
| **Prerequisites** | Management VLAN (Phase 3.2). AMT must not be reachable from untrusted networks. |

---

## Definition of Done

- [ ] Staging cluster operational, used for all upgrades before production
- [ ] Falco alerting on anomalous runtime behavior
- [ ] Weekly chaos experiments running without manual intervention
- [ ] Image signatures verified at admission
- [ ] Remote management available for all hosts
