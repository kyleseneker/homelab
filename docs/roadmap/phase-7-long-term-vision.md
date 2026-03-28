# Phase 7 -- Long-Term Vision

**Status:** Not started

Items worth tracking but not planned in detail. These become relevant as earlier phases are completed and the platform matures.

---

| Item | What | When It Makes Sense |
|------|------|-------------------|
| **Third compute host** | 3-node Proxmox cluster with Ceph or shared storage | When workload density outgrows 2 hosts, or if distributed storage is desired |
| **Declarative infrastructure** | Crossplane or Cluster API to manage Proxmox VMs and AWS resources from Kubernetes CRDs | When Terraform/Ansible maintenance overhead becomes a pain point, or as a platform engineering learning exercise |
| **Multi-cluster GitOps** | Single ArgoCD managing staging + production + future clusters | When the second cluster is stable and patterns are proven |
| **Dedicated GPU** | Low-profile GPU in the MS-01's PCIe x16 slot (e.g., Intel Arc A380) | When iGPU transcoding hits limits, or for ML/AI workloads |
| **Full 10G fabric** | Replace USW-16-PoE with a switch that has SFP+ uplinks; 10G to NAS | When NFS throughput is a bottleneck or a NAS with 10GbE is added |
| **IPv6** | Dual-stack networking across VLANs and Kubernetes | When ISP provides native IPv6 and external access is in use |
| **GitOps for network config** | Version-control UniFi firewall rules and VLAN config | When network changes are frequent enough to warrant it |
| **IoT VLAN** | Dedicated VLAN for smart home devices, isolated from household and homelab traffic | When IoT devices are added to the network |
| **HPA for workloads** | Horizontal Pod Autoscaler for Authentik, Grafana, and high-traffic apps | When traffic patterns justify scaling beyond fixed replica counts |
