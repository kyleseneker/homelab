# Homelab

Infrastructure-as-code for a self-hosted Kubernetes homelab. Ansible configures Proxmox hosts, Terraform provisions VMs, Ansible bootstraps Kubernetes clusters, and ArgoCD manages workloads via GitOps.

## At a Glance

| Host | Hardware | Role | Clusters |
|------|----------|------|----------|
| homelabpve01 | Minisforum MS-01 (64GB) | Proxmox VE | homelabk8s01 |

| Cluster | Nodes | Purpose |
|---------|-------|---------|
| homelabk8s01 | 1 control plane + 2 workers | *arr media stack, Jellyfin |

## How It All Fits Together

```mermaid
flowchart LR
    subgraph iac [Infrastructure as Code]
        Ansible1["Ansible"]
        Terraform["Terraform"]
        Ansible2["Ansible"]
    end

    subgraph platform [Platform]
        Proxmox["Proxmox VE"]
        VMs["Ubuntu VMs"]
        K8s["Kubernetes"]
    end

    subgraph gitops [GitOps]
        Git["Git Repo"]
        ArgoCD["ArgoCD"]
    end

    subgraph workloads [Workloads]
        Infra["Infrastructure"]
        Apps["Applications"]
    end

    Ansible1 -->|"configure host"| Proxmox
    Terraform -->|"provision VMs"| VMs
    Proxmox --- VMs
    Ansible2 -->|"bootstrap cluster"| K8s
    VMs --- K8s
    Git -->|"source of truth"| ArgoCD
    ArgoCD -->|"sync"| Infra
    ArgoCD -->|"sync"| Apps
    K8s --- ArgoCD
```

## Documentation

| Section | What You'll Find |
|---------|-----------------|
| [Getting Started](getting-started/quick-start.md) | Prerequisites, deployment walkthrough, configuration reference |
| [Architecture](architecture/overview.md) | System design, GitOps flow, networking, storage, monitoring |
| [Apps](apps/index.md) | Per-app details for the *arr stack, Jellyfin, and Homepage |
| [Infrastructure](infrastructure/index.md) | Every infrastructure component: charts, config, and integration |
| [Runbooks](runbooks/disaster-recovery.md) | Operational procedures: DR, upgrades, troubleshooting |
| [Reference](reference/commands.md) | Makefile commands, service URLs, repo layout |

