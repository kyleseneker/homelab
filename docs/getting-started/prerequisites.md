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
- A `/data` share created and exported to the subnet your K8s nodes will use

## Credentials

### PIA VPN

A **Private Internet Access** (PIA) VPN subscription. You will need your PIA username and password to create the VPN secret used by the Gluetun container in the *arr stack.

## Local Machine

Install the following tools on the machine you will run deployments from:

| Tool | Purpose |
|------|---------|
| [Terraform](https://developer.hashicorp.com/terraform/install) | Provision VMs on Proxmox |
| [Ansible](https://docs.ansible.com/ansible/latest/installation_guide/) | Configure Proxmox hosts and bootstrap Kubernetes |
| [kubectl](https://kubernetes.io/docs/tasks/tools/) | Interact with the Kubernetes cluster |
| [kubeseal](https://github.com/bitnami-labs/sealed-secrets#kubeseal) | Encrypt secrets for Sealed Secrets controller |
| [Velero CLI](https://velero.io/docs/main/basic-install/) | Manage cluster backups |
| SSH key pair | Used by Terraform and Ansible to access VMs |

!!! tip
    Run `make deps` to install most of these dependencies automatically. See the [Quick Start](quick-start.md) for details.

## What You Do NOT Need to Set Up Manually

Everything else is automated by `make pve-configure`, including:

- Cloning the required repositories to the Proxmox host
- Enabling IOMMU / PCI passthrough
- Creating the cloud-init VM template
- Generating a Proxmox API token for Terraform

You only need a fresh Proxmox VE install with root SSH access to get started.
