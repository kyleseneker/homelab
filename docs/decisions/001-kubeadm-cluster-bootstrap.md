# ADR-001: kubeadm Cluster Bootstrap with Packer, Terraform, and Ansible

## Status

Accepted

## Context

The cluster needs a repeatable provisioning pipeline that can build Kubernetes nodes from scratch on Proxmox, configure them, and bootstrap a kubeadm cluster without manual intervention beyond running the pipeline.

## Decision

Use a three-stage pipeline: Packer builds Ubuntu 24.04 VM templates with cloud-init autoinstall, Terraform clones those templates into Proxmox VMs with per-node resource specs, and Ansible orchestrates kubeadm cluster bootstrap in four phases (base setup + prerequisites, GPU passthrough, control plane init, worker join).

kubeadm initializes the cluster with Kubernetes 1.31.4, skipping the `addon/kube-proxy` phase to allow a CNI plugin to handle proxy duties. Ansible installs the chosen CNI immediately after `kubeadm init` to bring the cluster network online.

## Alternatives Considered

- **k3s**: Single-binary distribution with built-in networking and storage. Simpler to install but bundles Flannel and Traefik by default. Stripping out k3s defaults to replace them with a different CNI eliminates most of the simplicity benefit.
- **Talos Linux**: Immutable, API-driven OS purpose-built for Kubernetes. Attractive for security and reproducibility, but no SSH access makes GPU passthrough configuration and ad-hoc debugging significantly harder on a homelab where hardware experimentation is expected.
- **Managed Kubernetes (EKS, GKE)**: No infrastructure to manage, but adds cloud cost, latency to local services, and removes the learning value of self-hosting.
- **kind / minikube**: Development-only. Not suitable for persistent workloads or bare-metal features like GPU passthrough and L2 networking.

## Rationale

- **Full control**: kubeadm provides a standard Kubernetes cluster without vendor abstractions. Every component (CNI, CSI, ingress) is explicitly chosen rather than bundled.
- **GPU passthrough**: Packer's cloud-init and Terraform's PCI passthrough configuration enable Intel iGPU assignment to specific VMs for hardware transcoding. k3s and Talos make this harder due to their opinionated node setup.
- **Reproducibility**: Packer → Terraform → Ansible is fully idempotent. A cluster can be torn down and rebuilt from zero by re-running the pipeline.
- **Learning value**: Operating kubeadm exposes real Kubernetes internals (etcd, API server audit policy, kubelet configuration) that abstracted distributions hide.
- **Audit logging**: The kubeadm configuration template includes a custom audit policy (RequestResponse for secrets/RBAC/auth, Metadata for mutations) baked into the control plane from day one.

## Consequences

- kubeadm upgrades require manual Ansible playbook runs. There is no automatic control plane upgrade mechanism.
- The pipeline assumes Proxmox as the hypervisor. Migrating to different infrastructure would require replacing the Terraform provider and Packer builder.
- containerd is installed from Docker's apt repository and must be kept in sync with Kubernetes version compatibility.
