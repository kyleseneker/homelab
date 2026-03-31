# Phase 2 -- Kubernetes Hardening

**Status:** In progress

**Goal:** Close the software gaps that could cause outages or security incidents under normal operation.

**Addresses:** [K3, K7, K9, K11, K15](assessment.md#kubernetes--software-layer), [N6](assessment.md#network-layer)

---

## 2.1 Add ResourceQuotas and LimitRanges

- [ ] Define a default `LimitRange` for every namespace (default CPU/memory requests and limits)
- [ ] Define a `ResourceQuota` per namespace (hard ceiling on total resource consumption)
- [ ] Use Goldilocks/VPA recommendations to inform initial values
- [ ] Deploy via Kustomize components or per-namespace manifests
- [ ] Start generous, tighten based on observed usage

| | |
|---|---|
| **Why** | A single misbehaving pod can consume all node memory and cascade-kill neighbors. On 56 GB total worker RAM, one pod can cause a cluster-wide outage. |

## 2.2 Add Pod Topology Spread Constraints

- [ ] Add `topologySpreadConstraints` to: Authentik, Grafana, Prometheus, ArgoCD, Vault
- [ ] Use `whenUnsatisfiable: ScheduleAnyway` (soft constraint) to avoid blocking on a 3-node cluster
- [ ] Verify pods distribute across nodes after rollout

| | |
|---|---|
| **Why** | Without topology hints, the scheduler may co-locate critical services on one node. A single node failure could take out auth, monitoring, and GitOps simultaneously. |

## 2.3 Move Prometheus Storage Off NFS

- [ ] Migrate Prometheus PVC from `nfs-client` to `local-path` storage class
- [ ] Verify Prometheus retains metrics across the migration (or accept a clean start)
- [ ] Confirm Velero daily backup includes the local-path volume

| | |
|---|---|
| **Why** | Prometheus TSDB does heavy random I/O. NFS adds latency, causes scrape timeouts as cardinality grows, and risks TSDB corruption. |
| **Trade-off** | local-path ties Prometheus to a specific node. If that node fails, metrics history is lost until restored from backup. Acceptable -- metrics are diagnostic, not archival. |
| **Future** | If long-term retention becomes important, consider Thanos or Grafana Mimir with object-store backends. |

## 2.4 Add Image Registry Allowlist

- [ ] Create a Kyverno `ClusterPolicy` restricting image pulls to trusted registries
- [ ] Allowlist: `docker.io`, `ghcr.io`, `quay.io`, `registry.k8s.io`, `lscr.io`, and any others in use
- [ ] Verify all existing workloads pass the new policy before enforcing

| | |
|---|---|
| **Why** | Currently any registry is allowed. A typo or malicious upstream could pull from an untrusted source. |

## 2.5 cert-manager Health Alerting

- [ ] Add PrometheusRules for cert-manager pod readiness
- [ ] Add PrometheusRules for certificate renewal failures (`certmanager_certificate_ready_status == 0`)
- [ ] Add PrometheusRules for issuer errors

| | |
|---|---|
| **Why** | Existing alerts fire when a certificate is 14 days from expiry. But if cert-manager is dead, renewals silently stop and the alert only fires when expiry is imminent. |

## 2.6 Restrict Pod Egress to Known Destinations

- [ ] Audit current pod egress patterns (DNS, NFS, external APIs, container registries)
- [ ] Add CiliumNetworkPolicy `egressDeny` or implicit-deny rules per namespace
- [ ] Allowlist required destinations: DNS (kube-dns), NFS (192.168.1.158), and service-specific external endpoints
- [ ] Verify all workloads function after applying policies

| | |
|---|---|
| **Why** | A compromised pod can reach any external destination. Restricting egress limits the blast radius of a container breakout or supply chain attack. |
| **Approach** | Use Cilium's implicit deny model (allow specific egress, deny all else). Do **not** combine `egressDeny` world CIDRs with `egress` allow rules on the same policy -- this causes silent drops due to Cilium policy evaluation order. |

---

## Definition of Done

- [ ] Every namespace has a ResourceQuota and LimitRange
- [ ] Critical pods spread across nodes
- [ ] Prometheus running on local-path storage
- [ ] Only trusted registries allowed
- [ ] cert-manager failures trigger alerts
- [ ] Pod egress restricted to known destinations per namespace
