# Homelab

Infrastructure-as-code for my homelab. Ansible configures Proxmox hosts, Terraform provisions VMs, Ansible bootstraps Kubernetes clusters, and ArgoCD manages workloads via GitOps.

## Naming Convention

| Type | Pattern | Examples |
|------|---------|----------|
| Proxmox host | `homelabpve##` | `homelabpve01`, `homelabpve02` |
| K8s cluster | `homelabk8s##` | `homelabk8s01`, `homelabk8s02` |
| K8s node | `<cluster>-node-#` | `homelabk8s01-node-1`, `homelabk8s01-node-2` |

## Infrastructure

| Host | Hardware | Role | Clusters |
|------|----------|------|----------|
| homelabpve01 | Minisforum MS-01 (64GB) | Proxmox VE | homelabk8s01 |

| Cluster | Nodes | Purpose |
|---------|-------|---------|
| homelabk8s01 | 1 control plane + 2 workers | *arr media stack, Jellyfin |

## Quick Start

```bash
# 1. Install dependencies
make deps

# 2. Configure Proxmox host inventory
# Edit ansible/inventory/homelabpve01/hosts.yml with the PVE host IP

# 3. Configure Proxmox host (repos, IOMMU, cloud-init template, API token)
make pve-configure
# Save the API token printed at the end

# 4. Configure Terraform
cp terraform/hosts/homelabk8s01/terraform.tfvars.example terraform/hosts/homelabk8s01/terraform.tfvars
# Edit terraform.tfvars with your API token, IPs, SSH key, node definitions

# 5. Configure Ansible
# Edit ansible/inventory/homelabk8s01/hosts.yml -- node IPs must match terraform.tfvars
# Edit ansible/group_vars/all/vars.yml -- timezone, nas_ip, media_uid, media_gid

# 6. Configure K8s manifests
# Edit the files listed in the Configuration section below

# 7. Create VPN secret
cp k8s/clusters/homelabk8s01/apps/arr/vpn-secret.example k8s/clusters/homelabk8s01/apps/arr/vpn-secret.yml
# Edit with real PIA credentials

# 8. Deploy everything
make k8s-deploy

# 9. Apply VPN secret
make k8s-kubeconfig
export KUBECONFIG=$(pwd)/kubeconfig
kubectl apply -f k8s/clusters/homelabk8s01/apps/arr/vpn-secret.yml

# 10. Open ArgoCD dashboard
make k8s-dashboard
```

## Configuration

Each tool uses its own standard config file. Edit them directly.

### Terraform (`terraform/hosts/homelabk8s01/terraform.tfvars`)

Copy `terraform.tfvars.example` to `terraform.tfvars` and edit. Nodes are defined as a map -- add or remove entries to change cluster topology:

```hcl
nodes = {
  homelabk8s01-node-1 = {
    role   = "control-plane"
    ip     = "192.168.10.50/24"
    vm_id  = 200
    cores  = 2
    memory = 8192
  }
  homelabk8s01-node-2 = {
    role   = "worker"
    ip     = "192.168.10.51/24"
    vm_id  = 201
    cores  = 4
    memory = 24576
  }
  homelabk8s01-node-3 = {
    role        = "worker"
    ip          = "192.168.10.52/24"
    vm_id       = 202
    cores       = 4
    memory      = 24576
    tags        = ["gpu"]
    pci_devices = [{ id = "0000:00:02.0" }]
  }
}
```

### Ansible (`ansible/group_vars/all/vars.yml`)

| Variable | Description |
|----------|-------------|
| `timezone` | TZ database timezone |
| `nas_ip` | NAS / NFS server IP |
| `media_uid` | UID for media containers |
| `media_gid` | GID for media containers |

### Ansible inventory

| File | What to edit |
|------|-------------|
| `ansible/inventory/homelabpve01/hosts.yml` | Proxmox host IP |
| `ansible/inventory/homelabk8s01/hosts.yml` | K8s node IPs (must match terraform.tfvars) |

### K8s manifests

| File | What to edit |
|------|-------------|
| `k8s/clusters/homelabk8s01/config/env.yml` | TZ, PUID, PGID for *arr pods |
| `k8s/clusters/homelabk8s01/infrastructure/metallb/ip-pool.yml` | LoadBalancer IP range |
| `k8s/clusters/homelabk8s01/infrastructure/nfs-provisioner/application.yml` | NAS IP |
| `k8s/clusters/homelabk8s01/apps/arr/shared-data-pv.yml` | NAS IP |
| `k8s/clusters/homelabk8s01/apps/arr/gluetun-qbit-sab/application.yml` | VPN region |
| `k8s/bootstrap/root-app.yml` | Git repo URL |

## Commands

`pve-*` targets accept `PVE_HOST=<name>` (default: `homelabpve01`).
`k8s-*` targets accept `CLUSTER=<name>` (default: `homelabk8s01`).

```
make help             Show all commands
make deps             Install Ansible Galaxy collections
make vault-create     Create an empty vault.yml
make vault-edit       Edit encrypted vault.yml
make vault-encrypt    Encrypt vault.yml
make vault-decrypt    Decrypt vault.yml
make pve-configure    Configure Proxmox host
make pve-ssh          SSH into Proxmox host
make k8s-init         Initialize Terraform
make k8s-plan         Preview VM changes
make k8s-infra        Provision VMs on Proxmox
make k8s-configure    Bootstrap K8s cluster via Ansible
make k8s-deploy       Full deploy (VMs + cluster + ArgoCD)
make k8s-destroy      Tear down all VMs
make k8s-bootstrap    Install ArgoCD + root app (one-time)
make k8s-dashboard    Port-forward ArgoCD UI
make k8s-kubeconfig   Copy kubeconfig locally
make k8s-ssh-cp       SSH into control plane
```

Examples: `make PVE_HOST=homelabpve02 pve-configure`, `make CLUSTER=homelabk8s02 k8s-deploy`

## Architecture

- **kubeadm**: Vanilla upstream Kubernetes
- **Cilium**: eBPF-based CNI with Hubble observability
- **ArgoCD**: GitOps -- this repo is the source of truth
- **MetalLB**: LoadBalancer IPs from homelab VLAN
- **ingress-nginx**: Hostname-based routing to services
- **NFS provisioner**: Dynamic PVs from Unifi NAS
- **VPN sidecar**: Gluetun + download clients in one Pod (shared network namespace)
- **iGPU passthrough**: Jellyfin/Tdarr hardware transcoding via PCI passthrough

## Adding a New Proxmox Host

1. Create `ansible/inventory/<pve-host>/hosts.yml` with the host IP and `ansible_user: root`
2. Run `make PVE_HOST=<pve-host> pve-configure`

## Adding a New Worker

1. Add an entry to `nodes` in `terraform/hosts/<cluster>/terraform.tfvars`
2. Add the host to `ansible/inventory/<cluster>/hosts.yml` (under `workers`, and `gpu` if applicable)
3. Run `make k8s-infra && make k8s-configure`

## Adding a New Cluster

1. Create `terraform/hosts/<cluster>/` -- copy from an existing cluster, adjust `terraform.tfvars`
2. Create `ansible/inventory/<cluster>/hosts.yml` with the new node IPs
3. Create `k8s/clusters/<cluster>/` with its own `config/`, `infrastructure/`, and `apps/`
4. Update `k8s/bootstrap/root-app.yml` path (or create a second root-app for the new cluster)
5. Run `make CLUSTER=<cluster> k8s-deploy`

## NAS Folder Structure

Create on the Unifi NAS under the NFS share:

```
/data
├── torrents/{movies,tv,music,books}
├── usenet/{movies,tv,music,books}
└── media/{movies,tv,music,books}
```

## Prerequisites

1. **Proxmox VE**: Installed on the host with SSH access as root
2. **Unifi NAS**: NFS enabled, `/data` share created
3. **PIA**: VPN username and password
4. **Local machine**: Terraform, Ansible, kubectl, SSH key pair

Everything else (repos, IOMMU, cloud-init template, API token) is automated by `make pve-configure`.

## Post-Deploy

Access each *arr service via ingress or NodePort to complete initial setup:

1. **Prowlarr** -- Add indexers
2. **Sonarr/Radarr/Lidarr/Readarr** -- Root folders, connect Prowlarr + download clients
3. **qBittorrent** -- Check logs for initial password
4. **Jellyfin** -- Add media libraries
5. **Jellyseerr** -- Connect to Jellyfin, Sonarr, Radarr
6. **Bazarr** -- Connect to Sonarr, Radarr
7. **Tdarr** -- Configure transcode settings

## Repo Layout

```
homelab/
├── Makefile
├── terraform/
│   ├── modules/proxmox-vm/
│   └── hosts/<cluster>/
│       ├── terraform.tfvars.example
│       ├── variables.tf
│       ├── main.tf
│       └── outputs.tf
├── ansible/
│   ├── ansible.cfg
│   ├── requirements.yml
│   ├── playbooks/
│   │   ├── pve-host.yml
│   │   └── k8s-cluster.yml
│   ├── inventory/
│   │   ├── <pve-host>/hosts.yml
│   │   └── <cluster>/hosts.yml
│   ├── roles/
│   └── group_vars/all/
│       └── vars.yml
├── k8s/
│   ├── bootstrap/
│   │   ├── argocd/
│   │   └── root-app.yml
│   └── clusters/<cluster>/
│       ├── config/env.yml
│       ├── infrastructure/
│       └── apps/
├── .editorconfig
├── .gitignore
└── README.md
```
