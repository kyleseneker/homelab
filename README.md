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
# Edit ansible/inventory/homelabk8s01/group_vars/all.yml -- nas_ip, nas_export_path, nfs_mount_path
# Edit ansible/group_vars/all/vars.yml -- timezone, media_uid, media_gid

# 6. Configure K8s manifests
# Edit the files listed in the Configuration section below

# 7. Create secrets
cp k8s/clusters/homelabk8s01/apps/arr/vpn-secret.example k8s/clusters/homelabk8s01/apps/arr/vpn-secret.yml
# Edit vpn-secret.yml with real PIA credentials
cp k8s/clusters/homelabk8s01/apps/arr/recyclarr-secret.example k8s/clusters/homelabk8s01/apps/arr/recyclarr-secret.yml
# Edit recyclarr-secret.yml with Sonarr/Radarr API keys (after initial setup)

# 8. Deploy everything
make k8s-deploy

# 9. Apply secrets
make k8s-kubeconfig
export KUBECONFIG=$(pwd)/kubeconfig
kubectl apply -f k8s/clusters/homelabk8s01/apps/arr/vpn-secret.yml
kubectl apply -f k8s/clusters/homelabk8s01/apps/arr/recyclarr-secret.yml

# 10. Open ArgoCD at https://argocd.homelab.local
#     Get the initial admin password:
kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath="{.data.password}" | base64 -d; echo
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
| `media_uid` | UID for media containers |
| `media_gid` | GID for media containers |

### Ansible inventory

| File | What to edit |
|------|-------------|
| `ansible/inventory/homelabpve01/hosts.yml` | Proxmox host IP |
| `ansible/inventory/homelabk8s01/hosts.yml` | K8s node IPs (must match terraform.tfvars) |
| `ansible/inventory/homelabk8s01/group_vars/all.yml` | NAS IP, NFS export path, mount path |

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
make k8s-secrets      Apply VPN and Recyclarr secrets
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
- **Prometheus + Grafana + Loki**: Full cluster monitoring, dashboards, and log aggregation

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

After `make k8s-deploy` completes and ArgoCD syncs all applications, configure each service. Quality profiles and custom formats are already codified via Recyclarr -- the steps below cover the one-time settings stored in each app's database.

```bash
make k8s-kubeconfig
export KUBECONFIG=$(pwd)/kubeconfig
kubectl get pods -n arr   # verify everything is Running (recyclarr is a CronJob)
```

### 1. qBittorrent

Get the initial random admin password:

```bash
kubectl logs -n arr -l app.kubernetes.io/instance=arr-vpn-downloads -c qbittorrent | grep "temporary password"
```

Open `https://qbit.homelab.local`, log in as `admin` with that password. Go to **Tools > Options > Web UI** and change the password.

### 2. SABnzbd

Open `https://sabnzbd.homelab.local`. Complete the first-time wizard to set language and add your Usenet provider (server address, port, username, password, SSL, connections). If the wizard doesn't appear, go to **Config > Servers**.

### 3. Sonarr / Radarr

For each app (`https://sonarr.homelab.local`, `https://radarr.homelab.local`):

**Authentication:** Settings > General > Authentication > Forms. Set a username and password.

**Root folders** (Settings > Media Management > Root Folders):

| App | Root Folder |
|-----|-------------|
| Sonarr | `/data/media/tv` |
| Radarr | `/data/media/movies` |

**Download clients** (Settings > Download Clients > Add):

| Setting | qBittorrent | SABnzbd |
|---------|-------------|---------|
| Host | `arr-vpn-downloads.arr.svc.cluster.local` | `arr-vpn-downloads.arr.svc.cluster.local` |
| Port | `8080` | `8085` |
| Auth | admin + your password | API key from SABnzbd Config > General |
| Category | `tv` / `movies` (per app) | `tv` / `movies` (per app) |

**Note the API key** from Settings > General -- you'll need it for Prowlarr and Recyclarr.

### 4. Prowlarr

Open `https://prowlarr.homelab.local`. Prowlarr is a centralized indexer manager -- add indexers here once and they sync to all *arr apps automatically.

**Authentication:** Settings > General > Authentication > Forms. Set a username and password.

**Add indexers:** Indexers > Add Indexer. Search for your torrent tracker or Usenet indexer by name, then enter the API key or credentials for each.

**Connect to *arr apps:** Settings > Apps > Add Application. Add each one using API keys from step 3:

| App | Prowlarr Server | App Server URL |
|-----|-----------------|----------------|
| Sonarr | `http://arr-prowlarr.arr.svc.cluster.local:9696` | `http://arr-sonarr.arr.svc.cluster.local:8989` |
| Radarr | `http://arr-prowlarr.arr.svc.cluster.local:9696` | `http://arr-radarr.arr.svc.cluster.local:7878` |

After saving, click **Sync App Indexers** and verify indexers appear in each *arr app under Settings > Indexers.

### 5. Recyclarr

Quality profiles and custom formats are already defined in `k8s/clusters/homelabk8s01/apps/arr/recyclarr/configmap.yml`. Recyclarr just needs API keys to apply them.

```bash
cp k8s/clusters/homelabk8s01/apps/arr/recyclarr-secret.example recyclarr-secret.yml
# Edit recyclarr-secret.yml -- paste API keys from Sonarr and Radarr (Settings > General)
make k8s-secrets
rm recyclarr-secret.yml
```

To trigger a sync immediately instead of waiting for the next 6-hour CronJob run:

```bash
kubectl create job --from=cronjob/arr-recyclarr -n arr recyclarr-manual
kubectl logs -n arr -l job-name=recyclarr-manual -f
```

### 6. Jellyfin

Open `https://jellyfin.homelab.local`. Follow the setup wizard to create an admin user, then add media libraries:

| Library | Content Type | Path |
|---------|-------------|------|
| Movies | Movies | `/data/media/movies` |
| TV Shows | Shows | `/data/media/tv` |
| Music | Music | `/data/media/music` |

Enable hardware transcoding: **Dashboard > Playback > Transcoding > Intel QuickSync** (the iGPU is already passed through).

### 7. Jellyseerr

Open `https://jellyseerr.homelab.local`.

- Sign in with Jellyfin: use `http://arr-jellyfin.arr.svc.cluster.local:8096` as the server URL
- Add Sonarr: `http://arr-sonarr.arr.svc.cluster.local:8989` + API key
- Add Radarr: `http://arr-radarr.arr.svc.cluster.local:7878` + API key

### 8. Bazarr

Open `https://bazarr.homelab.local`.

- Settings > Sonarr: `http://arr-sonarr.arr.svc.cluster.local:8989` + API key
- Settings > Radarr: `http://arr-radarr.arr.svc.cluster.local:7878` + API key
- Settings > Subtitles: Add subtitle providers (OpenSubtitles, etc.)

### 9. Tdarr

Open `https://tdarr.homelab.local`.

- Libraries: Add `/data/media/movies` and `/data/media/tv`
- Transcode settings: Choose target codec (H.265/HEVC recommended for space savings)
- The Intel iGPU is already available for hardware transcoding

### 10. Homepage Dashboard

The dashboard is available at `https://home.homelab.local`. To enable service widgets, create the API key secret:

```bash
cp k8s/clusters/homelabk8s01/apps/homepage/homepage-secret.example homepage-secret.yml
# Edit homepage-secret.yml with API keys from each service (Settings > General)
kubectl apply -f homepage-secret.yml
rm homepage-secret.yml
kubectl rollout restart deployment/homepage -n arr
```

### 11. Monitoring & Observability

The cluster deploys a full monitoring stack automatically via ArgoCD:

| Component | Purpose |
|-----------|---------|
| Metrics Server | `kubectl top nodes` / `kubectl top pods` |
| Prometheus | Cluster and app metrics, alerting rules |
| Grafana | Dashboards and log exploration |
| Loki | Log aggregation (single-binary mode) |
| Alloy | DaemonSet log collector shipping to Loki |
| Alertmanager | Alert routing (ready for future rules) |
| Node Exporter | Host-level metrics from every node |
| Kube State Metrics | Kubernetes object metrics |

**Grafana** is available at `https://grafana.homelab.local`.

- Default login: `admin` / `admin` (change on first login)
- Pre-built dashboards for cluster, node, pod, and namespace health are included
- Loki is pre-configured as a data source -- use **Explore** to search logs by namespace, pod, or container

Add a DNS entry for `grafana.homelab.local` pointing to the ingress LoadBalancer IP (same as other `*.homelab.local` entries).

### Trust the Homelab CA (one-time per machine)

To avoid self-signed certificate warnings in your browser:

```bash
export KUBECONFIG=$(pwd)/kubeconfig
kubectl get secret homelab-ca-secret -n cert-manager -o jsonpath='{.data.tls\.crt}' | base64 -d > homelab-ca.crt
sudo security add-trusted-cert -d -r trustRoot -k /Library/Keychains/System.keychain homelab-ca.crt
rm homelab-ca.crt
```

Restart your browser after running this. All `https://*.homelab.local` sites will show valid certificates.

### Internal Service URLs

Reference for app-to-app connections (Kubernetes service DNS):

| Service | URL |
|---------|-----|
| Sonarr | `http://arr-sonarr.arr.svc.cluster.local:8989` |
| Radarr | `http://arr-radarr.arr.svc.cluster.local:7878` |
| Prowlarr | `http://arr-prowlarr.arr.svc.cluster.local:9696` |
| Bazarr | `http://arr-bazarr.arr.svc.cluster.local:6767` |
| Jellyfin | `http://arr-jellyfin.arr.svc.cluster.local:8096` |
| Jellyseerr | `http://arr-jellyseerr.arr.svc.cluster.local:5055` |
| qBittorrent | `http://arr-vpn-downloads.arr.svc.cluster.local:8080` |
| SABnzbd | `http://arr-vpn-downloads.arr.svc.cluster.local:8085` |
| Tdarr | `http://arr-tdarr.arr.svc.cluster.local:8265` |

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
│       │   ├── metrics-server/
│       │   ├── kube-prometheus-stack/
│       │   ├── loki/
│       │   ├── alloy/
│       │   └── ...
│       └── apps/
├── .editorconfig
├── .gitignore
└── README.md
```
