# Commands

All operational commands are defined as Makefile targets. Proxmox targets (`pve-*`) accept `PVE_HOST=<name>` (default: `homelabpve01`). Kubernetes targets (`k8s-*`) accept `CLUSTER=<name>` (default: `homelabk8s01`).

## Documentation

| Command | Description |
|---------|-------------|
| `make docs` | Build documentation site |
| `make docs-serve` | Serve documentation site locally |

## Setup

| Command | Description |
|---------|-------------|
| `make deps` | Install Ansible Galaxy collections |
| `make vault-create` | Create an empty vault.yml and encrypt it |
| `make vault-edit` | Edit vault.yml (decrypts in-place, re-encrypts on save) |
| `make vault-encrypt` | Encrypt vault.yml |
| `make vault-decrypt` | Decrypt vault.yml (for manual editing) |

## Packer

| Command | Description |
|---------|-------------|
| `make packer-init` | Initialize Packer plugins |
| `make packer-validate` | Validate Packer template |
| `make packer-build` | Build K8s node VM template on Proxmox |

## Proxmox

| Command | Description |
|---------|-------------|
| `make pve-configure` | Configure Proxmox host (repos, IOMMU, cloud-init, API token) |
| `make pve-ssh` | SSH into Proxmox host |

## Kubernetes

| Command | Description |
|---------|-------------|
| `make k8s-init` | Initialize Terraform for K8s VMs |
| `make k8s-plan` | Preview K8s VM changes |
| `make k8s-infra` | Provision K8s VMs on Proxmox |
| `make k8s-configure` | Bootstrap K8s cluster via Ansible |
| `make k8s-deploy` | Full deploy: VMs + cluster + ArgoCD |
| `make k8s-destroy` | Tear down all K8s VMs |
| `make k8s-bootstrap` | Install ArgoCD and the ApplicationSet (one-time) |
| `make k8s-backup` | Trigger an on-demand Velero backup |
| `make k8s-backup-status` | Show Velero backup and schedule status |
| `make k8s-restore` | List available Velero backups for restore |
| `make k8s-kubeconfig` | Copy kubeconfig from control plane to local machine |
| `make k8s-ssh-cp` | SSH into control plane |
| `make cilium-upgrade` | Upgrade Cilium with Gateway API and L2 announcements on an existing cluster |

## Validation

| Command | Description |
|---------|-------------|
| `make k8s-render` | Render every ApplicationSet manifest locally and diff `k8s/bootstrap/` against the cluster -- the same check CI runs |
| `make k8s-check-alerts` | Verify every alert selector matches a live Prometheus series |

Run `make k8s-render` before pushing any change under `k8s/`. It is the only check that exercises `config.yml` and `values.yml`, which kubeconform skips.

## HashiCorp Vault

| Command | Description |
|---------|-------------|
| `make vault-init` | Initialize Vault and configure ESO integration (one-time) |
| `make vault-put-secret` | Write a secret to Vault (`SECRET_PATH=... KEY=... VAL=...`) |
| `make vault-status` | Show Vault seal status |
| `make arr-keys-adopt` | Copy each *arr app's live API key into Vault at `homelab/apps/arr` (never prints the key) |

## AWS

Provisions the KMS key backing Vault auto-unseal and the IAM user for offsite Velero backups.

| Command | Description |
|---------|-------------|
| `make aws-init` | Initialize Terraform for AWS resources |
| `make aws-plan` | Preview AWS resource changes |
| `make aws-apply` | Provision the AWS KMS key and IAM user for Vault auto-unseal |

## Examples

Override the default host or cluster by passing variables to `make`:

```bash
make PVE_HOST=homelabpve02 pve-configure
make CLUSTER=homelabk8s02 k8s-deploy
```
