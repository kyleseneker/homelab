# Homelab

Infrastructure-as-code for a self-hosted Kubernetes homelab. Ansible configures Proxmox hosts, Packer builds VM templates, Terraform provisions VMs, Ansible bootstraps Kubernetes clusters, and ArgoCD manages workloads via GitOps.

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
        Packer["Packer"]
        Terraform["Terraform"]
        Ansible2["Ansible"]
    end

    subgraph platform [Platform]
        Proxmox["Proxmox VE"]
        Template["VM Template"]
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
    Packer -->|"build template"| Template
    Proxmox --- Template
    Terraform -->|"clone & provision"| VMs
    Template --- VMs
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
| [Apps](apps/index.md) | Per-app details for the *arr stack, Jellyfin, Homepage, Exportarr, and Uptime Kuma |
| [Infrastructure](infrastructure/index.md) | Every infrastructure component: charts, config, and integration |
| [Runbooks](runbooks/disaster-recovery.md) | Operational procedures: DR, upgrades, troubleshooting |
| [Reference](reference/commands.md) | Makefile commands, service URLs, repo layout |
