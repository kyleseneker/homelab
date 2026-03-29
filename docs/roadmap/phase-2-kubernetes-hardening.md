# Phase 2 -- Kubernetes Hardening

**Status:** In progress

**Goal:** Close the software gaps that could cause outages or security incidents under normal operation.

**Addresses:** [K2, K3, K6, K7, K9, K11, K15, K17](assessment.md#kubernetes--software-layer), [N6](assessment.md#network-layer)

---

## 2.1 Promote Kyverno Policies to Enforce

- [x] Review current Kyverno policy reports for existing violations
- [x] Fix any violations in existing workloads
- [x] Update exclusion lists as needed (linuxserver images, GPU operator, etc.)
- [x] Promote `require-resource-limits` to enforce
- [x] Promote `require-run-as-nonroot` to enforce
- [x] Promote `require-readonly-rootfs` to enforce

| | |
|---|---|
| **Why** | Audit-mode policies only generate reports. A misconfigured deployment slips through without blocking. |
| **Approach** | Flip one policy at a time. Validate each in a staging window before the next. |

## 2.2 Add ResourceQuotas and LimitRanges

- [ ] Define a default `LimitRange` for every namespace (default CPU/memory requests and limits)
- [ ] Define a `ResourceQuota` per namespace (hard ceiling on total resource consumption)
- [ ] Use Goldilocks/VPA recommendations to inform initial values
- [ ] Deploy via Kustomize components or per-namespace manifests
- [ ] Start generous, tighten based on observed usage

| | |
|---|---|
| **Why** | A single misbehaving pod can consume all node memory and cascade-kill neighbors. On 56 GB total worker RAM, one pod can cause a cluster-wide outage. |

## 2.3 Enable Authentik Redis Authentication

- [ ] Set `auth.enabled: true` on the Authentik Redis subchart
- [ ] Store the Redis password in Vault
- [ ] Create an ExternalSecret to sync the password
- [ ] Verify Authentik server and worker can connect with the new credentials

| | |
|---|---|
| **Why** | Redis currently accepts unauthenticated connections. Any pod in the auth namespace can read/write the session cache. |

## 2.4 Add Pod Topology Spread Constraints

- [ ] Add `topologySpreadConstraints` to: Authentik, Grafana, Prometheus, ArgoCD, Vault
- [ ] Use `whenUnsatisfiable: ScheduleAnyway` (soft constraint) to avoid blocking on a 3-node cluster
- [ ] Verify pods distribute across nodes after rollout

| | |
|---|---|
| **Why** | Without topology hints, the scheduler may co-locate critical services on one node. A single node failure could take out auth, monitoring, and GitOps simultaneously. |

## 2.5 Move Prometheus Storage Off NFS

- [ ] Migrate Prometheus PVC from `nfs-client` to `local-path` storage class
- [ ] Verify Prometheus retains metrics across the migration (or accept a clean start)
- [ ] Confirm Velero daily backup includes the local-path volume

| | |
|---|---|
| **Why** | Prometheus TSDB does heavy random I/O. NFS adds latency, causes scrape timeouts as cardinality grows, and risks TSDB corruption. |
| **Trade-off** | local-path ties Prometheus to a specific node. If that node fails, metrics history is lost until restored from backup. Acceptable -- metrics are diagnostic, not archival. |
| **Future** | If long-term retention becomes important, consider Thanos or Grafana Mimir with object-store backends. |

## 2.6 Add Image Registry Allowlist

- [ ] Create a Kyverno `ClusterPolicy` restricting image pulls to trusted registries
- [ ] Allowlist: `docker.io`, `ghcr.io`, `quay.io`, `registry.k8s.io`, `lscr.io`, and any others in use
- [ ] Verify all existing workloads pass the new policy before enforcing

| | |
|---|---|
| **Why** | Currently any registry is allowed. A typo or malicious upstream could pull from an untrusted source. |

## 2.7 cert-manager Health Alerting

- [ ] Add PrometheusRules for cert-manager pod readiness
- [ ] Add PrometheusRules for certificate renewal failures (`certmanager_certificate_ready_status == 0`)
- [ ] Add PrometheusRules for issuer errors

| | |
|---|---|
| **Why** | Existing alerts fire when a certificate is 14 days from expiry. But if cert-manager is dead, renewals silently stop and the alert only fires when expiry is imminent. |

## 2.8 Configure Loki Retention Policy

- [ ] Set `limits_config.retention_period` in Loki configuration (e.g., 30 days)
- [ ] Enable the compactor for log retention enforcement
- [ ] Verify old logs are pruned after the retention window
- [ ] Monitor Loki storage usage via Prometheus

| | |
|---|---|
| **Why** | Loki currently stores logs indefinitely on NFS. Without retention, storage grows unbounded and NFS performance degrades over time. |

## 2.9 Restrict Pod Egress to Known Destinations

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

- [x] All three Kyverno audit-mode policies promoted to enforce
- [ ] Every namespace has a ResourceQuota and LimitRange
- [ ] Authentik Redis requires authentication
- [ ] Critical pods spread across nodes
- [ ] Prometheus running on local-path storage
- [ ] Only trusted registries allowed
- [ ] cert-manager failures trigger alerts
- [ ] Loki retention policy enforced, storage bounded
- [ ] Pod egress restricted to known destinations per namespace
