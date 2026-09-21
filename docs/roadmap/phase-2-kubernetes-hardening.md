# Phase 2 — Kubernetes Hardening

**Status:** In progress. Enforce-mode Kyverno policies, selected Cilium policies, resource limits and operational alerts already exist.

**Goal:** Run a supported and maintainable cluster with explicit access and capacity boundaries. Addresses K2, K3, K9, K11, K15, K34 and K42–K49 in the [assessment](assessment.md).

## 2.1 Upgrade the unsupported platform

The cluster and provisioning configuration use Kubernetes 1.31.4. Kubernetes 1.31 reached end of life on 2025-11-11. A version-string change does not upgrade existing nodes. Follow the [staged upgrade runbook](../runbooks/upgrading-kubernetes.md) and the [upstream release status](https://kubernetes.io/releases/1.31/).

- [ ] Inventory running Kubernetes, kubeadm/kubelet, containerd, Cilium, Gateway CRDs and etcd versions.
- [ ] Select a supported destination and verify the complete compatibility matrix against primary release documentation.
- [ ] Rehearse each intermediate minor upgrade with an isolated restore and a rollback/rebuild path.
- [ ] Upgrade one minor at a time; retain and test compatible etcd backup/restore tooling.
- [ ] Update Packer, Ansible, CLI pins, schema target and runbooks together. Demonstrate both an upgrade and a fresh node join.

## 2.2 Make least privilege real

- [ ] Deploy the audit/Alloy fixes and confirm secret and token payloads no longer enter new logs. Assess access to retained historical logs separately.
- [ ] Verify that the deployed OpenClaw ServiceAccount cannot mutate nodes.
- [ ] Exercise each Kyverno rule with violating regular and init containers, plus legitimate privileged infrastructure exceptions.
- [ ] Replace blanket namespace exceptions incrementally where workloads actually conform; do not enable enforcement by breaking essential controllers.
- [ ] Measure egress and management reachability before tightening policies in working namespaces.
- [ ] Inventory provisioning API-token permissions, endpoint TLS trust and floating tool/runtime versions; reduce broad credentials and replace trust bypasses with configured CA trust.
- [ ] Verify Secret rotation updates dependent workloads, including reloads or restarts where required.
- [ ] Evaluate an image registry allowlist after enumerating the current image sources. A permitted registry is not proof of trustworthy provenance.

## 2.3 Budget resources and maintenance

- [ ] Use at least a representative workload cycle of VPA/Prometheus and OOM history to set namespace budgets.
- [ ] Add measured ResourceQuotas and selected LimitRanges with room for upgrade surge, Jobs and recovery. Avoid arbitrary limits on all system namespaces.
- [ ] Add root-disk headroom and local-path directory visibility; PVC capacity declarations do not enforce a directory quota.
- [ ] Document singleton `minAvailable:1` PDB handling for a planned drain. It can block eviction but cannot keep a failed singleton available.
- [ ] Apply topology spread to multi-replica stateless services when placement can improve availability. Respect node affinity and local storage.
- [ ] Verify certificate readiness, expiry and missing metrics alerts independently.

## Definition of Done

The cluster is on a supported, tested version combination; denied operations are proven; a worker can be drained and returned with a documented downtime expectation; capacity alerts correspond to actual storage and memory constraints.
