# Architecture Overview

This document provides a high-level view of the homelab infrastructure, covering the full provisioning pipeline, component inventory, and naming conventions.

## Provisioning Pipeline

The homelab is provisioned through a multi-stage pipeline that takes bare-metal hardware to a fully operational Kubernetes cluster running production-grade workloads.

```mermaid
flowchart LR
    subgraph stage1["Stage 1: Hypervisor"]
        ansible1["Ansible"] --> proxmox["Proxmox VE"]
    end

    subgraph stage2["Stage 2: Virtual Machines"]
        terraform["Terraform"] --> vms["VM Instances"]
    end

    subgraph stage3["Stage 3: Kubernetes"]
        ansible2["Ansible"] --> kubeadm["kubeadm Cluster"]
    end

    subgraph stage4["Stage 4: Workloads"]
        argocd["ArgoCD"] --> apps["Applications"]
    end

    stage1 --> stage2
    stage2 --> stage3
    stage3 --> stage4
```

**Stage 1 -- Hypervisor Provisioning:** Ansible configures the Proxmox VE hypervisor nodes, managing host-level settings, storage pools, and network bridges.

**Stage 2 -- VM Provisioning:** Terraform provisions virtual machines on Proxmox, defining compute resources, disk layouts, and cloud-init configuration for each Kubernetes node.

**Stage 3 -- Kubernetes Bootstrap:** Ansible installs and configures the kubeadm-based Kubernetes cluster, handling container runtime setup, control plane initialization, worker node joins, and CNI (Cilium) deployment.

**Stage 4 -- Workload Deployment:** ArgoCD manages all cluster workloads declaratively via GitOps. An app-of-apps pattern with directory recursion deploys infrastructure components and applications in the correct order using sync waves.

## Component Inventory

| Component | Role | Namespace |
|------|------|-----------|
| Cilium | Container Network Interface (CNI) | `kube-system` |
| ArgoCD | GitOps continuous delivery | `argocd` |
| MetalLB | Bare-metal LoadBalancer IP allocation | `metallb-system` |
| ingress-nginx | Ingress controller (DaemonSet mode) | `ingress-nginx` |
| cert-manager | TLS certificate management (self-signed CA) | `cert-manager` |
| Sealed Secrets | Encrypted secret management | `kube-system` |
| NFS Provisioner | Dynamic NFS-backed PVC provisioning | `nfs-provisioner` |
| Metrics Server | Kubernetes resource metrics API | `kube-system` |
| MinIO | S3-compatible object storage for backups | `backups` |
| Intel GPU Operator | Intel GPU device driver management | `intel-gpu-operator` |
| Intel GPU Plugin | Intel iGPU device plugin for workloads | `intel-gpu-operator` |
| kube-prometheus-stack | Prometheus, Grafana, Alertmanager, Node Exporter, kube-state-metrics | `monitoring` |
| Loki | Log aggregation (single-binary mode) | `monitoring` |
| Velero | Cluster and volume backup/restore | `backups` |
| Alloy | DaemonSet log collector | `monitoring` |
| Authentik | SSO provider (forward-auth + OIDC) | `auth` |
| Reloader | Automatic pod restarts on ConfigMap/Secret changes | `kube-system` |
| Descheduler | Pod rebalancing across nodes (CronJob) | `kube-system` |
| Jellyfin | Media server | `arr` |
| Sonarr | TV series management | `arr` |
| Radarr | Movie management | `arr` |
| Prowlarr | Indexer management | `arr` |
| Bazarr | Subtitle management | `arr` |
| Jellyseerr | Media request management | `arr` |
| qBittorrent | Torrent client (via Gluetun VPN sidecar) | `arr` |
| Recyclarr | Quality profile sync (CronJob) | `arr` |
| Tdarr | Media transcoding | `arr` |
| Exportarr | Prometheus exporter for *arr app metrics | `arr` |
| Homepage | Dashboard | `arr` |
| Uptime Kuma | Synthetic monitoring and status page | `monitoring` |

## Naming Conventions

Consistent naming across the infrastructure simplifies management, documentation, and troubleshooting.

| Pattern | Example | Description |
|---|---|---|
| `homelabpve##` | `homelabpve01` | Proxmox VE hypervisor nodes |
| `homelabk8s##` | `homelabk8s01` | Kubernetes cluster identifiers |
| `cluster-node-#` | `homelabk8s01-node-1` | Individual Kubernetes nodes within a cluster |

## Repository Structure

The repository is organized by tool and cluster:

```
homelab/
  ansible/           # Playbooks for Proxmox and K8s provisioning
  terraform/         # VM provisioning on Proxmox
  k8s/
    bootstrap/       # ArgoCD bootstrap and root application
    clusters/
      homelabk8s01/  # Cluster-specific ArgoCD Applications
        apps/        # Application workloads
        infrastructure/  # Infrastructure components
  docs/              # MkDocs documentation
```

!!! info "Single Source of Truth"
    The Git repository is the single source of truth for all cluster state. Manual changes made directly to the cluster will be detected and reverted by ArgoCD's automated sync with pruning and self-healing enabled.
