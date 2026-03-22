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
  description = "VM template ID to clone from"
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
