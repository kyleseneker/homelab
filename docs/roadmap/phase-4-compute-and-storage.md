# Phase 4 -- Compute & Storage

**Status:** Not started

**Goal:** Eliminate the single-host and single-controller dependencies.

**Addresses:** [P4](assessment.md#physical-layer) (single compute host), [K1](assessment.md#kubernetes--software-layer) (single control plane), [K4](assessment.md#kubernetes--software-layer) (Vault standalone)

---

## 4.1 Add a Second Compute Host

- [ ] Purchase a second Minisforum MS-01 (or equivalent)
- [ ] Install in the rack, connect SFP+ to the 10G switch (Phase 3.1)
- [ ] Add to Proxmox as a cluster node
- [ ] Add the new host to the Ansible inventory and run `pve-host.yml`
- [ ] Redistribute Kubernetes VMs across both hosts in Terraform
- [ ] Update [hardware inventory](../reference/hardware.md)
- [ ] Write an ADR

| | |
|---|---|
| **Why** | All VMs run on one machine. Hardware failure means total cluster loss with no recovery until hardware is replaced. |
| **Unlocks** | Proxmox HA (automatic VM failover), rolling Proxmox upgrades, rolling K8s upgrades without downtime, proper pod anti-affinity. |
| **Sizing** | A matching MS-01 with 64 GB RAM is ideal. A smaller node (32 GB) is sufficient for one worker and one control plane node. |
| **IaC** | The existing Terraform module and Ansible inventory are parameterized. Adding a host means a new `target_node` and rebalancing VM placement. |

## 4.2 Expand to 3 Control Plane Nodes

- [ ] Provision 2 additional control plane VMs (spread across both hosts)
- [ ] Deploy a load balancer in front of the API server (kube-vip or HAProxy)
- [ ] Join new nodes with `kubeadm join --control-plane`
- [ ] Add a `k8s_control_plane_join` Ansible role (or conditional in existing role)
- [ ] Verify etcd quorum with `etcdctl member list`
- [ ] Update kubeconfig to use the load balancer endpoint
- [ ] Write an ADR

| | |
|---|---|
| **Why** | Single control plane means API server, etcd, and scheduler are all SPOFs. 3 nodes across 2 hosts survives any single failure. |
| **Prerequisites** | Second compute host (4.1). Load balancer for API server. |
| **Resource cost** | ~2 vCPU and 4-8 GB RAM per control plane node. With 128 GB across 2 hosts, easily accommodated. |

## 4.3 Migrate Vault to HA (Raft)

- [ ] Switch Vault from standalone file storage to integrated Raft storage (3 replicas)
- [ ] Move Vault PVCs from `nfs-client` to `local-path` (Raft needs local disk)
- [ ] Verify AWS KMS auto-unseal works for all replicas
- [ ] Verify ESO can reach Vault through a Vault service (not a specific pod)
- [ ] Test failover: kill the Raft leader, confirm a new leader is elected
- [ ] Write an ADR

| | |
|---|---|
| **Why** | Vault is a single pod. If it crashes or NFS stalls, every ExternalSecret stops refreshing. New deployments and secret rotations fail immediately. |
| **Approach** | Vault's integrated Raft replicates data across replicas without a separate etcd or Consul cluster. All replicas use the same KMS key for auto-unseal. |

## 4.4 Expand NAS Storage

- [ ] Add 2 more drives to the UNAS Pro (4 total)
- [ ] Reconfigure as RAID 10 (16 TB usable, redundancy + read performance)
- [ ] Verify NFS exports and Kubernetes PVCs
- [ ] Update [hardware inventory](../reference/hardware.md)

| | |
|---|---|
| **Why** | With the Phase 1.2 mirror, usable capacity is 8 TB. RAID 10 doubles usable space and improves read performance. |
| **Timing** | Flexible. Monitor with the existing `NFSStorageLow` PrometheusRule alert. |

---

## Definition of Done

- [ ] Kubernetes VMs distributed across 2 physical hosts
- [ ] 3 control plane nodes with etcd quorum, surviving single node failure
- [ ] Vault running in HA mode with Raft storage
- [ ] NAS storage expanded
