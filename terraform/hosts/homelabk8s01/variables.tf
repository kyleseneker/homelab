variable "proxmox_endpoint" {
  type        = string
  description = "Proxmox API URL"
}

variable "proxmox_api_token" {
  type      = string
  sensitive = true
}

variable "proxmox_insecure" {
  type    = bool
  default = true
}

variable "target_node" {
  type        = string
  description = "Proxmox node name"
}

variable "clone_template_id" {
  type        = number
  default     = 9000
  description = "VM template ID to clone"
}

variable "ssh_public_key" {
  type        = string
  description = "SSH public key for cloud-init user"
}

variable "nameserver" {
  type        = string
  description = "DNS server IP"
}

variable "gateway" {
  type        = string
  description = "Network gateway IP"
}

variable "nodes" {
  type = map(object({
    role         = string
    ip           = string
    vm_id        = number
    cores        = optional(number, 4)
    memory       = optional(number, 16384)
    disk_size    = optional(number, 32)
    tags         = optional(list(string), [])
    pci_mappings = optional(list(string), [])
  }))
  description = "Map of VM definitions keyed by hostname"
}

variable "bridge" {
  type        = string
  default     = "vmbr0"
  description = "Proxmox bridge used by the cluster VMs"
}

variable "username" {
  type        = string
  default     = "media"
  description = "Cloud-init administrator username"
}

variable "agent_enabled" {
  type        = bool
  default     = true
  description = "Enable the QEMU guest agent; requires an image containing the agent"
}

variable "onboot" {
  type        = bool
  default     = true
  description = "Start cluster VMs automatically with the Proxmox host"
}

variable "tags" {
  type        = list(string)
  default     = ["k8s"]
  description = "Tags shared by every cluster VM, in addition to its role and node tags"
}

variable "nic_vlan_id" {
  type        = number
  default     = null
  description = "VLAN tag for the VM NICs. Set to 1 only once the bridge is VLAN-aware, making each NIC an access port on the native VLAN (ADR-016)"
}

variable "l2_pool_cidrs" {
  type        = list(string)
  default     = []
  description = "Cilium L2 LoadBalancer pool; with the node's own address, the only sources its NIC may send from. Empty leaves the VM firewall off (ADR-016)"
}
