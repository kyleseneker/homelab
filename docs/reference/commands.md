# Commands

All operational commands are defined as Makefile targets. Proxmox targets (`pve-*`) accept `PVE_HOST=<name>` (default: `homelabpve01`). Kubernetes targets (`k8s-*`) accept `CLUSTER=<name>` (default: `homelabk8s01`).

### Documentation

| Command | Description |
|---------|-------------|
| `make docs` | Build documentation site |
| `make docs-serve` | Serve documentation site locally |

### Setup

| Command | Description |
|---------|-------------|
| `make deps` | Install Ansible Galaxy collections |
| `make vault-create` | Create an empty vault.yml and encrypt it |
| `make vault-edit` | Edit vault.yml (decrypts in-place, re-encrypts on save) |
| `make vault-encrypt` | Encrypt vault.yml |
| `make vault-decrypt` | Decrypt vault.yml (for manual editing) |

### Proxmox

| Command | Description |
|---------|-------------|
| `make pve-configure` | Configure Proxmox host (repos, IOMMU, cloud-init, API token) |
| `make pve-ssh` | SSH into Proxmox host |

### Kubernetes

| Command | Description |
|---------|-------------|
| `make k8s-init` | Initialize Terraform for K8s VMs |
| `make k8s-plan` | Preview K8s VM changes |
| `make k8s-infra` | Provision K8s VMs on Proxmox |
| `make k8s-configure` | Bootstrap K8s cluster via Ansible |
| `make k8s-deploy` | Full deploy: VMs + cluster + ArgoCD |
| `make k8s-destroy` | Tear down all K8s VMs |
| `make k8s-bootstrap` | Install ArgoCD and root app-of-apps (one-time) |
| `make k8s-seal` | Seal a plaintext secret (`FILE=path/to/secret.yml`) |
| `make k8s-backup-sealed-key` | Back up Sealed Secrets controller private key |
| `make k8s-backup` | Trigger an on-demand Velero backup |
| `make k8s-backup-status` | Show Velero backup and schedule status |
| `make k8s-restore` | List available Velero backups for restore |
| `make k8s-kubeconfig` | Copy kubeconfig from control plane to local machine |
| `make k8s-ssh-cp` | SSH into control plane |

### Examples

Override the default host or cluster by passing variables to `make`:

```bash
make PVE_HOST=homelabpve02 pve-configure
make CLUSTER=homelabk8s02 k8s-deploy
```
