# Configuration Reference

This page documents every file you need to edit before deploying the homelab. Values like IP addresses, credentials, and resource allocations are specific to your environment and must be configured manually.

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

The `tags` and `pci_devices` fields are used to pass an Intel iGPU through to a worker node for hardware transcoding in Jellyfin and Tdarr.

## Ansible

### Global Variables

**File:** `ansible/group_vars/all/vars.yml`

| Variable | Description |
|----------|-------------|
| `timezone` | Timezone for all nodes (e.g. `America/Chicago`) |
| `media_uid` | UID for the shared media user across NFS and pods |
| `media_gid` | GID for the shared media group across NFS and pods |

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
| `k8s/clusters/homelabk8s01/config/env.yml` | `TZ`, `PUID`, `PGID` for *arr pods |
| `k8s/components/metallb-config/ip-pool.yml` | LoadBalancer IP range for MetalLB |
| `k8s/clusters/homelabk8s01/infrastructure/nfs-provisioner/application.yml` | NAS IP address for the NFS provisioner |
| `k8s/clusters/homelabk8s01/apps/arr/shared-data-pv.yml` | NAS IP address for the shared media PersistentVolume |
| `k8s/clusters/homelabk8s01/apps/arr/gluetun-qbit-sab/application.yml` | VPN server region |
| `k8s/bootstrap/root-app.yml` | Git repository URL for ArgoCD |

!!! tip
    After editing these files, commit the changes to your Git repository. ArgoCD will pick up the new configuration on its next sync cycle.
