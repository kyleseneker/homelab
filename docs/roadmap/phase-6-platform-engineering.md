# Phase 6 — Platform Engineering

**Status:** In progress. CI renders manifests, validates schemas and tests tooling; scoped OpenClaw remediation is configured. Staging, Falco, chaos testing and admission-time signature verification remain planned.

**Goal:** Build a platform engineering practice with repeatable promotion, runtime security, failure experiments and supply-chain verification.

**Addresses:** K12, K13, K18, K22, K23 and K47 in the [assessment](assessment.md), alongside upgrade and recovery validation.

## 6.1 Staging Cluster

- [ ] Provision a second Kubernetes cluster (one control plane and one worker) on the second host from Phase 4.1.
- [ ] Configure ArgoCD ApplicationSet discovery with a separate staging overlay or branch.
- [ ] Establish a staging → production promotion workflow.
- [ ] Use staging for Kubernetes upgrades and Cilium version changes before production.
- [ ] Rehearse bootstrap, worker replacement and application restores.
- [ ] Give staging distinct credentials, application endpoints and writable storage paths.

The second host provides capacity for a persistent staging cluster. Use the existing [restore lab](../runbooks/restore-lab.md) on disposable VMs while that hardware work is underway, and carry its bootstrap and acceptance checks into staging.

## 6.2 Runtime Security with Falco

- [ ] Deploy Falco as a DaemonSet in staging, then production.
- [ ] Deploy Falcosidekick to route alerts to Alertmanager.
- [ ] Tune rules for homelab workloads, including expected shells and maintenance operations.
- [ ] Verify unexpected shell execution, sensitive-file access and other supported detections reach Slack through the existing alerting path.

Falco adds runtime behavior detection alongside admission policies and network controls.

## 6.3 Chaos Engineering

- [ ] Select Litmus or Chaos Mesh and deploy it in staging.
- [ ] Start with pod-kill experiments and verify expected recovery.
- [ ] Add node cordon/drain, NFS interruption and DNS failure experiments with defined scope and abort criteria.
- [ ] Schedule weekly experiments during low-traffic hours after validating them manually.
- [ ] Document results and feed recovery gaps back into runbooks and implementation work.

Use staging for destructive experiments. Expand production experiments only when the affected workloads, recovery behavior and acceptable interruption are understood.

## 6.4 Supply Chain Security

- [ ] Confirm the next Renovate run discovers the intended chart and image dependencies.
- [ ] Scan relevant workload images as well as source manifests, keeping exceptions scoped.
- [ ] Add Kyverno cosign verification for images with supported publisher identities and signatures; define treatment of unsigned dependencies before enforcement.
- [ ] Evaluate Harbor as a pull-through registry cache with vulnerability scanning.

Signature verification establishes provenance from a configured signer. Scanning and dependency updates address separate supply-chain concerns.

## 6.5 Scoped Autonomous Operations

- [ ] Verify Slack pairing and webhook authentication independently.
- [ ] Record remediation target, reason, before/after state and outcome.
- [ ] Review write-capable media API credentials separately from Kubernetes permissions.

## Definition of Done

- [ ] The staging cluster is used for upgrades and promotion before production.
- [ ] Falco alerts on tested anomalous runtime behavior.
- [ ] Weekly scoped chaos experiments run and record recovery results.
- [ ] Image signatures are verified at admission for the defined image set.
- [ ] Autonomous remediation has verified access limits and recorded outcomes.
