# proxmox-vm

Reusable Terraform module for provisioning a Proxmox VM with cloud-init and optional PCI passthrough.

## Usage

```hcl
module "my_vm" {
  source = "../../modules/proxmox-vm"

  vm_name        = "my-vm"
  vm_id          = 100
  target_node    = "homelabpve01"
  cores          = 4
  memory         = 16384
  ip_address     = "10.0.10.50/24"
  gateway        = "10.0.10.1"
  ssh_public_key = "ssh-ed25519 AAAA..."

  # Optional: PCI passthrough (e.g. iGPU)
  pci_devices = [{ id = "0000:00:02.0" }]
}
```

## Inputs

| Name | Type | Default | Description |
|------|------|---------|-------------|
| vm_name | string | - | VM hostname |
| vm_id | number | - | Proxmox VM ID |
| target_node | string | - | Proxmox node name |
| cores | number | 4 | CPU cores |
| memory | number | 16384 | RAM in MB |
| disk_size | number | 32 | OS disk in GB |
| disk_storage | string | "local-lvm" | Proxmox storage pool |
| ip_address | string | - | Static IP with CIDR |
| gateway | string | - | Network gateway |
| ssh_public_key | string | - | SSH public key for cloud-init |
| cloud_init_image | string | "ubuntu-24.04-cloud" | Cloud-init template name |
| nameserver | string | "1.1.1.1" | DNS server |
| tags | list(string) | [] | Proxmox tags |
| pci_devices | list(object) | [] | PCI passthrough devices |
| onboot | bool | true | Start VM on host boot |
| started | bool | true | Start VM after creation |

## Outputs

| Name | Description |
|------|-------------|
| vm_id | Proxmox VM ID |
| vm_name | VM hostname |
| ip_address | Static IP (with CIDR) |
