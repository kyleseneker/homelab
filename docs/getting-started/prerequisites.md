# Prerequisites

Before deploying the homelab, ensure the following hardware, software, and credentials are in place.

## Hardware

### Proxmox Host

A machine running **Proxmox VE** with:

- SSH access as `root` (password or key-based)
- Sufficient CPU, memory, and storage for the Kubernetes VMs you plan to provision

### NAS

A **Unifi NAS** (or compatible NFS server) with:

- NFS enabled
- An NFS export allowed from the K8s node subnet, with its actual export path recorded consistently in Ansible and Kubernetes (the current UniFi export includes a volume UUID)

## Credentials

### PIA VPN

A **Private Internet Access** (PIA) VPN subscription. You will need your PIA username and password to create the VPN secret used by the Gluetun container in the *arr stack.

### AWS

An **AWS account**. Two things depend on it and neither is optional:

- **Vault auto-unseal** uses a KMS key. Without it, Vault stays sealed after every pod restart and every secret in the cluster is unavailable.
- **Offsite backups** use an S3 bucket for the weekly Velero backup and the nightly etcd snapshot.

`terraform/aws` provisions the KMS key and the IAM users. Run it before the first `make k8s-bootstrap` -- see [Configuration &rarr; AWS](configuration.md#aws).

## Local Machine

Install the following tools on the machine you will run deployments from:

| Tool | Purpose |
|------|---------|
| [Packer](https://developer.hashicorp.com/packer/install) | Build K8s node VM templates on Proxmox |
| [Terraform](https://developer.hashicorp.com/terraform/install) | Provision VMs on Proxmox |
| [Ansible](https://docs.ansible.com/ansible/latest/installation_guide/) | Configure Proxmox hosts and bootstrap Kubernetes |
| [kubectl](https://kubernetes.io/docs/tasks/tools/) | Interact with the Kubernetes cluster |
| [Vault CLI](https://developer.hashicorp.com/vault/install) | Manage secrets in HashiCorp Vault |
| [Velero CLI](https://velero.io/docs/main/basic-install/) | Manage cluster backups |
| [Helm](https://helm.sh/docs/intro/install/) + [kustomize](https://kubectl.docs.kubernetes.io/installation/kustomize/) | Required by `make k8s-render` |
| [AWS CLI](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html) | Retrieve offsite backups during disaster recovery |
| SSH key pair | Used by Terraform and Ansible to access VMs |

!!! tip
    Run `make deps` to install the required Ansible Galaxy collections. All other tools listed above must be installed manually.

## Bootstrap dependencies

Before `make pve-configure`, configure the host inventory, an HCP Terraform agent token, and a private UPS monitor password in Ansible Vault. The playbook configures IOMMU, host networking, UPS shutdown, the agent, and the Proxmox API token. Host networking changes and IOMMU reboots need a maintenance window and working console access.

Packer builds template `9000` separately with `make packer-build`. Authenticate to HCP Terraform and configure its two workspaces before provisioning. The private Proxmox workspace needs the configured agent pool; AWS credentials and the KMS bootstrap Secret must exist before Vault can start. See the [Quick Start](quick-start.md).
