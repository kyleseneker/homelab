# Configuration Reference

This page documents every file you need to edit before deploying the homelab. Values like IP addresses, credentials, and resource allocations are specific to your environment and must be configured manually.

## Packer

**File:** `packer/k8s-node/k8s-node.auto.pkrvars.hcl`

Copy the example file to get started:

```bash
cp packer/k8s-node/k8s-node.auto.pkrvars.hcl.example packer/k8s-node/k8s-node.auto.pkrvars.hcl
```

| Variable | Description | Default |
|----------|-------------|---------|
| `proxmox_url` | Proxmox API URL | *(required)* |
| `proxmox_api_token_id` | Proxmox API token ID | *(required)* |
| `proxmox_api_token_secret` | Proxmox API token secret | *(required)* |
| `proxmox_node` | Proxmox node to build the template on | *(required)* |
| `template_id` | VM ID for the resulting template | `9000` |
| `iso_url` | Ubuntu 24.04 server ISO URL | Ubuntu 24.04.2 LTS |
| `iso_checksum` | ISO checksum (file URL for automatic verification) | Ubuntu SHA256SUMS |
| `iso_storage_pool` | Proxmox storage pool for the ISO | `local` |
| `disk_storage_pool` | Proxmox storage pool for the VM disk | `local-lvm` |
| `k8s_version` | Kubernetes version to install (e.g. `1.31.4`) | `1.31.4` |
| `k8s_version_minor` | Kubernetes minor version for apt repo (e.g. `1.31`) | `1.31` |
| `timezone` | Timezone for the template | `America/Chicago` |
| `media_uid` | UID for the media user | `977` |
| `media_gid` | GID for the media group | `988` |

!!! note
    The `proxmox_api_token_id` and `proxmox_api_token_secret` are the same credentials used by Terraform. The `template_id` must match the `clone_template_id` variable in `terraform/hosts/<cluster>/variables.tf`.

## Terraform

**File:** `terraform/hosts/homelabk8s01/terraform.tfvars`

Copy the example file to get started:

```bash
cp terraform/hosts/homelabk8s01/terraform.tfvars.example terraform/hosts/homelabk8s01/terraform.tfvars
```

Nodes are defined as a map. Each entry specifies the VM role, IP address, Proxmox VM ID, CPU cores, and memory. Worker nodes can optionally include tags and PCI device passthrough:

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
    role         = "worker"
    ip           = "192.168.10.52/24"
    vm_id        = 202
    cores        = 4
    memory       = 24576
    tags         = ["gpu"]
    pci_mappings = ["igpu"]
  }
}
```

The `tags` and `pci_mappings` fields are used to pass an Intel iGPU through to a worker node for hardware transcoding in Jellyfin and Tdarr. The `pci_mappings` value references a Proxmox PCI device mapping created by the `pve-configure` playbook.

## Ansible

### Global Variables

**File:** `ansible/group_vars/all/vars.yml`

| Variable | Description | Default |
|----------|-------------|---------|
| `ansible_user` | SSH user on the provisioned VMs | `media` |
| `base_timezone` | Timezone for all nodes | `America/Chicago` |
| `base_media_uid` | UID for the shared media user across NFS and pods | `977` |
| `base_media_gid` | GID for the shared media group across NFS and pods | `988` |
| `k8s_control_plane_version` | Kubernetes version for `kubeadm init` | `1.31.4` |
| `k8s_control_plane_pod_network_cidr` | Pod CIDR passed to kubeadm | `10.244.0.0/16` |
| `k8s_control_plane_service_cidr` | Service CIDR passed to kubeadm | `10.96.0.0/12` |
| `k8s_control_plane_cilium_version` | Cilium version installed by the CLI | `1.19.1` |
| `k8s_prereqs_version` | Kubernetes package version on every node | `1.31.4` |
| `k8s_prereqs_version_minor` | Kubernetes minor version for the apt repo | `1.31` |

!!! note "Pod CIDR"
    `k8s_control_plane_pod_network_cidr` is what kubeadm records, but Cilium is installed with its default `cluster-pool` IPAM and allocates pod IPs from `10.0.0.0/8` regardless. The kubeadm value is not what pods actually get.

### Inventory Files

| File | What to edit |
|------|--------------|
| `ansible/inventory/homelabpve01/hosts.yml` | Proxmox host IP address |
| `ansible/inventory/homelabk8s01/hosts.yml` | K8s node IPs (must match the values in `terraform.tfvars`) |
| `ansible/inventory/homelabk8s01/group_vars/all.yml` | `nas_ip`, `nas_export_path`, `nfs_mount_path` |

!!! note
    The node IPs in the Ansible inventory **must** match the IPs defined in `terraform.tfvars`. A mismatch will cause Ansible to fail when it tries to connect to the provisioned VMs.

## Kubernetes Manifests

The following manifest files contain environment-specific values that must be edited before deployment:

| File | What to edit |
|------|--------------|
| `k8s/clusters/homelabk8s01/apps/arr/prereqs/env.yml` | `TZ`, `PUID`, `PGID` for *arr pods |
| `k8s/clusters/homelabk8s01/infrastructure/gateway/l2-pool.yml` | LoadBalancer IP range for Cilium L2 |
| `k8s/clusters/homelabk8s01/infrastructure/nfs-provisioner/values.yml` | NAS IP address for the NFS provisioner |
| `k8s/clusters/homelabk8s01/apps/arr/prereqs/shared-data-pv.yml` | NAS IP address **and export path** for the shared media PersistentVolume |
| `k8s/clusters/homelabk8s01/apps/arr/downloads/values.yml` | VPN server region |
| `k8s/clusters/homelabk8s01/infrastructure/velero/values.yml` | Offsite S3 bucket name and region |
| `k8s/clusters/homelabk8s01/infrastructure/etcd-backup/cronjob.yml` | Offsite S3 bucket for etcd snapshots |
| `k8s/bootstrap/applicationsets/cluster-apps.yml` | Git repository URL for ArgoCD (appears three times) |

!!! warning "The NAS export path contains a volume UUID"
    `shared-data-pv.yml` hardcodes a UniFi volume UUID that will be different on any replacement NAS. The same path is set independently in `ansible/inventory/<cluster>/group_vars/all.yml` as `nas_export_path`; both must agree.

## AWS

**Directory:** `terraform/aws`

Provisions the KMS key that backs Vault's auto-unseal and the IAM user Velero uses for offsite backups. Copy `terraform.tfvars.example` and run `make aws-init && make aws-apply`. The resulting key ID and access keys go into the `vault-aws-kms` Secret and into Vault at `infrastructure/velero-offsite` and `infrastructure/etcd-backup`.

!!! tip
    After editing these files, commit the changes to your Git repository. ArgoCD will pick up the new configuration on its next sync cycle.
