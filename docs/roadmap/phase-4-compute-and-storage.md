# Phase 4 -- Compute & Storage

**Status:** Not started

**Goal:** Expand compute and storage capacity, distribute workloads across hosts, and remove single-instance control-plane and Vault dependencies.

**Addresses:** P4, K1, and K4 in the [assessment](assessment.md).

---

## 4.1 Add a Second Compute Host

- [ ] Purchase a second Minisforum MS-01 (or equivalent)
- [ ] Install in the rack and connect SFP+ to the 10G switch ([Phase 3.1](phase-3-network.md#31-enable-10g-networking))
- [ ] Add to Proxmox as a cluster node
- [ ] Add the new host to the Ansible inventory and run `pve-host.yml`
- [ ] Redistribute Kubernetes VMs across both hosts in Terraform with explicit per-host placement
- [ ] Account for node-local disks and GPU passthrough when planning VM moves and host maintenance
- [ ] Configure quorum, fencing, and accessible VM storage if enabling Proxmox HA
- [ ] Update the [hardware inventory](../reference/hardware.md)

| | |
|---|---|
| **Why** | All VMs currently run on one machine. A second host adds capacity and lets workloads move off a host for planned maintenance. |
| **Sizing** | A matching MS-01 with 64 GB RAM is the target. A smaller 32 GB node is an alternative for one worker and one control-plane node. |
| **IaC** | Add host-specific Ansible inventory and Terraform placement, then rebalance the VM allocation. |
| **Availability** | Automatic VM failover also requires reliable quorum, fencing, and accessible VM data. See the [Proxmox HA requirements](https://pve.proxmox.com/pve-docs/chapter-ha-manager.html). GPU passthrough and node-local disks constrain migration. |

## 4.2 Expand to 3 Control Plane Nodes

- [ ] Provision two additional control-plane VMs, initially spread across both hosts
- [ ] Deploy a stable API endpoint with kube-vip or HAProxy and test endpoint failover
- [ ] Join new nodes with `kubeadm join --control-plane`, including certificate distribution
- [ ] Add a `k8s_control_plane_join` Ansible role or conditional in the existing role
- [ ] Verify etcd membership with `etcdctl member list` and cluster health
- [ ] Update kubeconfig and node bootstrap configuration to use the API endpoint
- [ ] Update etcd backup and replacement procedures for the three-member cluster
- [ ] Test loss of one control-plane VM and document behavior when each physical host is unavailable

| | |
|---|---|
| **Why** | Three control-plane nodes remove the single-VM dependency for the API server, etcd, and scheduler. |
| **Prerequisites** | Second compute host (4.1) and a stable API endpoint. |
| **Resource cost** | Approximately 2 vCPU and 4–8 GB RAM per additional control-plane node, within the planned 128 GB across two matching hosts. |
| **Failure tolerance** | Three etcd members survive loss of one member. With a 2+1 placement across two hosts, losing the host carrying two members loses quorum. Distribute one member per host when adding the [third host](phase-7-long-term-vision.md); a Proxmox quorum device does not vote in etcd. |

## 4.3 Migrate Vault to HA (Raft)

- [ ] Cut over production Vault to local integrated Raft storage using the verified migration and rollback procedure
- [ ] Configure three Vault replicas using integrated Raft storage
- [ ] Move Vault from NFS to durable local storage, with peer discovery and TLS configured
- [ ] Spread Raft voters across the available physical hosts; use one voter per host when the third host is added
- [ ] Verify AWS KMS auto-unseal works for all replicas
- [ ] Verify ESO reaches Vault through the Vault service
- [ ] Deploy recurring production Raft snapshots, offsite verification and freshness monitoring
- [ ] Test leader failover and document whole-host failure behavior for the deployed placement

| | |
|---|---|
| **Why** | Vault is a single pod on NFS. A pod or storage outage interrupts secret refreshes, new secret-dependent deployments, and rotations. |
| **Approach** | Integrated Raft replicates Vault data without a separate etcd or Consul cluster. All replicas use the same KMS key for auto-unseal. |
| **Migration** | Changing replica count or StorageClass does not migrate the existing file-storage backend. Migrate the data and replace file backups with Raft snapshots. |
| **Failure tolerance** | Three voters tolerate one voter failure. As with etcd, surviving either physical host's loss requires a third independent host. |

## 4.4 Expand NAS Storage

- [ ] Add two more 8 TB CMR drives to the NAS after the [Phase 1.1 mirror](phase-1-foundations.md#11-add-nas-drive-redundancy), for four installed drives total
- [ ] Confirm the exact UNAS model/firmware supports the intended four-drive RAID 10 layout and determine its migration procedure
- [ ] Take and verify an independent backup before changing the pool
- [ ] Expand to the planned 16 TB usable capacity with RAID 10; use backup/recreation/restore if an in-place transition is unsupported
- [ ] Verify NFS exports, paths, ownership, and Kubernetes PVCs after migration
- [ ] Update the [hardware inventory](../reference/hardware.md)

| | |
|---|---|
| **Why** | The Phase 1.1 mirror provides 8 TB usable capacity. Four 8 TB drives in RAID 10 target 16 TB usable before filesystem overhead, retaining drive redundancy. |
| **Timing** | Flexible. Track available capacity with the existing `NFSStorageLow` PrometheusRule alert. |

---

## Definition of Done

- [ ] Kubernetes VMs distributed across two physical hosts
- [ ] Three control-plane nodes with etcd quorum, surviving a single control-plane VM failure
- [ ] Stable API endpoint tested during control-plane failover
- [ ] Vault running with three Raft replicas, leader failover and snapshot recovery verified
- [ ] NAS expanded to the planned capacity with redundant storage
- [ ] Physical-host failure limitations recorded for the deployed two-host topology
