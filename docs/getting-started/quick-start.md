# Quick Start

A full walkthrough to go from a bare Proxmox host to a running Kubernetes cluster with all applications deployed via ArgoCD.

## 1. Install Dependencies

```bash
make deps
```

This installs the required Ansible Galaxy collections. All other tools (Terraform, Ansible, kubectl, vault CLI, Velero CLI) must be installed manually -- see [Prerequisites](../getting-started/prerequisites.md).

## 2. Configure Proxmox Host Inventory

Edit the Proxmox inventory file with the IP address of your Proxmox host:

```
ansible/inventory/homelabpve01/hosts.yml
```

## 3. Configure the Proxmox Host

```bash
make pve-configure
```

This Ansible playbook prepares the Proxmox host by enabling IOMMU, creating a cloud-init VM template, and generating a Proxmox API token for Terraform.

!!! warning
    Save the API token printed at the end of this step. You will need it for the Terraform configuration in the next step.

## 4. Build the K8s Node VM Template

Configure Packer variables:

```bash
cp packer/k8s-node/k8s-node.auto.pkrvars.hcl.example packer/k8s-node/k8s-node.auto.pkrvars.hcl
```

Edit `packer/k8s-node/k8s-node.auto.pkrvars.hcl` with your Proxmox API credentials, node name, ISO URL, and storage pools. See the [Configuration](configuration.md#packer) page for details.

Build the template:

```bash
make packer-init
make packer-build
```

This creates a K8s-ready VM template on Proxmox with Ubuntu 24.04, containerd, kubeadm, NFS client, and iGPU drivers pre-installed. Terraform will clone this template in the next step.

!!! note
    The template build takes roughly 10--15 minutes. The Packer build boots the ISO, runs Ubuntu autoinstall, then provisions the VM with Ansible roles before converting it to a template.

## 5. Configure Terraform

```bash
cp terraform/hosts/homelabk8s01/terraform.tfvars.example terraform/hosts/homelabk8s01/terraform.tfvars
```

Edit `terraform/hosts/homelabk8s01/terraform.tfvars` and fill in:

- The Proxmox API token from the previous step
- VM IP addresses
- SSH public key path
- Node definitions (roles, cores, memory, PCI devices)

See the [Configuration](configuration.md#terraform) page for a full reference.

## 6. Configure Ansible

Edit the following files:

| File | What to configure |
|------|-------------------|
| `ansible/inventory/homelabk8s01/hosts.yml` | K8s node IPs (must match the IPs in `terraform.tfvars`) |
| `ansible/inventory/homelabk8s01/group_vars/all.yml` | `nas_ip`, `nas_export_path`, `nfs_mount_path` |
| `ansible/group_vars/all/vars.yml` | `timezone`, `media_uid`, `media_gid` |

See the [Configuration](configuration.md#ansible) page for details.

## 7. Configure Kubernetes Manifests

Several K8s manifest files contain values specific to your environment (IP addresses, Git repo URL, timezone). See the [Configuration](configuration.md#kubernetes-manifests) page for the full list of files to edit.

## 8. Deploy Everything

```bash
make k8s-deploy
```

This single command will:

1. Provision VMs with Terraform
2. Bootstrap Kubernetes with kubeadm and Cilium via Ansible
3. Install ArgoCD and the root application

## 9. Get Kubeconfig and Initialize Vault

Retrieve the kubeconfig from the cluster:

```bash
make k8s-kubeconfig
export KUBECONFIG=$(pwd)/kubeconfig
```

Wait for Vault and ESO to be deployed by ArgoCD, then initialize Vault:

```bash
# Wait for Vault pod to be running
kubectl -n vault wait --for=condition=ready pod/vault-0 --timeout=300s

# Initialize Vault (one-time setup: unseal, enable KV v2, configure K8s auth)
make vault-init
```

!!! warning "Save the Unseal Key and Root Token"
    The init script prints an unseal key and root token. Store both in your password manager immediately. The unseal key is required after every Vault pod restart.

## 10. Populate Secrets in Vault

Write each secret to Vault. Each `*-external-secret.yml` manifest documents the Vault path and required keys:

```bash
# Port-forward to Vault
kubectl port-forward -n vault svc/vault 8200:8200 &
export VAULT_ADDR=http://127.0.0.1:8200
vault login  # enter root token

# VPN credentials
vault kv put homelab/apps/vpn \
  OPENVPN_USER=your_pia_username \
  OPENVPN_PASSWORD=your_pia_password

# MinIO credentials
vault kv put homelab/infrastructure/minio \
  rootUser=minioadmin \
  rootPassword=your_minio_password

# Repeat for all secrets -- see *-external-secret.yml manifests for the full list
```

ESO syncs secrets from Vault to Kubernetes automatically. Verify the sync status:

```bash
kubectl get externalsecret --all-namespaces
```

All ExternalSecrets should show `SecretSynced` status.

## 11. Access ArgoCD

Open [https://argocd.homelab.local](https://argocd.homelab.local) in your browser.

Retrieve the initial admin password:

```bash
kubectl -n argocd get secret argocd-initial-admin-secret \
  -o jsonpath="{.data.password}" | base64 -d; echo
```

Log in with username `admin` and the password from the command above. From the ArgoCD dashboard you can monitor the sync status of all applications as they deploy.

!!! note
    If your browser shows a certificate warning, see [Trust the Homelab CA](trust-ca.md) to install the root certificate on your machine.
