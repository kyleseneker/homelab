# Phase 7 -- Long-Term Vision

**Status:** Not started

Items worth tracking but not planned in detail. These become relevant as earlier phases are completed and the platform matures.

---

| Item | What | When It Makes Sense |
|------|------|-------------------|
| **Third compute host** | Three-node Proxmox cluster with Ceph or shared storage; one etcd and Vault voter per physical host | When workload density outgrows two hosts, distributed storage is desired, or quorum services need to survive loss of any one host |
| **Declarative infrastructure** | Crossplane or Cluster API to manage Proxmox VMs and AWS resources from Kubernetes CRDs | When Terraform/Ansible maintenance overhead becomes a pain point, or as a platform engineering learning exercise; assign one controller to each resource |
| **Multi-cluster GitOps** | Single ArgoCD managing staging, production, and future clusters | When the second cluster is stable and patterns are proven |
| **Dedicated GPU** | Low-profile GPU in the MS-01's PCIe x16 slot, with Intel Arc A380 as an option to evaluate for fit, power, and cooling | When iGPU transcoding hits limits, or for ML/AI workloads; verify the exact card meets the MS-01's half-height, single-slot constraints ([MS-01 specifications](https://store.minisforum.com/en-my/products/minisforum-ms-01)) |
| **Full 10G fabric** | Replace USW-16-PoE with a switch that has SFP+ uplinks; extend 10G to the NAS and compute hosts | As the rack grows beyond the initial 10G links in Phase 3.1 |
| **IPv6** | Dual-stack networking across VLANs and Kubernetes | When the ISP provides native IPv6 and external access is in use |
| **GitOps for network config** | Version-control UniFi firewall rules and VLAN configuration | When network changes are frequent enough to warrant it |
| **IoT VLAN** | Dedicated VLAN for smart home devices, isolated from household and homelab traffic | When IoT devices are added to the network |
| **HPA for workloads** | Horizontal Pod Autoscaler for Authentik, Grafana, and high-traffic apps, with shared/external state configured where required | When traffic patterns justify scaling beyond fixed replica counts |
