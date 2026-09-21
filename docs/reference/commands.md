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
| `make vault-create` | Create an empty vault.yml ready to edit and encrypt |
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
| `make k8s-deploy` | Ordered deploy: VMs + cluster + kubeconfig + ArgoCD |
| `make k8s-destroy` | Tear down all K8s VMs |
| `make k8s-bootstrap` | Install or update ArgoCD and the ApplicationSet |
| `make k8s-backup` | Trigger an on-demand Velero backup |
| `make k8s-backup-status` | Show Velero backup and schedule status |
| `make k8s-restore` | List available Velero backups for restore |
| `make k8s-kubeconfig` | Copy kubeconfig from control plane to local machine |
| `make k8s-ssh-cp` | SSH into control plane |
| `make cilium-upgrade` | Upgrade Cilium with Gateway API and L2 announcements on an existing cluster |

## Restore Lab

Use these dedicated targets for `homelabrestore01`; do not pass the lab to the production bootstrap. See the [restore lab runbook](../runbooks/restore-lab.md) for first-time workspace setup.

| Command | Description |
|---------|-------------|
| `make lab-host` | Configure the isolated bridge, firewall, template and scoped API identity |
| `make lab-init` | Initialize the separate Terraform workspace |
| `make lab-plan` | Preview lab VM changes |
| `make lab-infra` | Provision the two lab VMs |
| `make lab-configure` | Bootstrap Kubernetes without production storage or applications |
| `make lab-tunnel` | Forward the lab API to localhost:16443 through Proxmox |
| `make lab-kubeconfig` | Fetch credentials into `.lab/kubeconfig` |
| `make lab-status` | Check lab node readiness |
| `make lab-ssh` | SSH to the lab control plane through Proxmox |
| `make lab-disconnect` | Close the API tunnel |
| `make lab-destroy` | Destroy only lab VMs, retaining the host setup and credentials |

## Validation

| Command | Description |
|---------|-------------|
| `make k8s-render` | Render Helm/Kustomize resources and validate their schemas without contacting the cluster |
| `make k8s-bootstrap-drift` | Compare manually managed bootstrap resources with the live cluster; differences and API errors fail |
| `make k8s-crd-schemas` | Generate schemas from pinned media-operator charts and vendored Gateway CRDs |
| `make k8s-check-alerts` | Audit current series referenced by local alert and recording rules |

Run `make k8s-render` before pushing any change under `k8s/`. It is the only check that exercises `config.yml` and `values.yml`, which kubeconform skips.

## HashiCorp Vault

| Command | Description |
|---------|-------------|
| `make vault-init` | Initialize Vault and configure ESO integration (one-time) |
| `make vault-put-secret` | Patch one Vault field safely (`SECRET_PATH=... KEY=...`, export `VAL`) |
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

## Credentials and context

Make defaults `KUBECONFIG` to the repository's kubeconfig. Set it explicitly when using another cluster; `CLUSTER` selects Terraform/inventory paths but does not verify the API server identity. The ordered deployment fetches its kubeconfig before applying bootstrap resources.

Vault helper commands own and clean up their port-forward. If port 8200 is occupied they fail without stopping the other process; set `VAULT_PORT` to an available local port. Export the token and secret value without placing them in shell history, for example:

```bash
read -rs VAL
export VAL
make vault-put-secret SECRET_PATH=infrastructure/minio KEY=rootPassword
unset VAL
```

The helper patches existing KV v2 data. Its create fallback uses CAS 0 and cannot overwrite an existing secret after a failed patch. A concurrent change or insufficient permissions fails explicitly.

The alert audit uses Prometheus's experimental `parse_query` endpoint and fails explicitly on unsupported responses. It skips selectors used only inside absence functions, while checking the same selector used outside them. It checks current presence, not historical coverage, thresholds, joins, deployed-rule drift or notification delivery. Exit 1 means missing series; exit 2 means a parsing/API/query error.
