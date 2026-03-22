variable "vm_name" {
  type = string
}

variable "vm_id" {
  type = number
}

variable "target_node" {
  type = string
}

variable "cores" {
  type    = number
  default = 4
}

variable "memory" {
  type    = number
  default = 16384
}

variable "disk_size" {
  type    = number
  default = 32
}

variable "disk_storage" {
  type    = string
  default = "local-lvm"
}

variable "ip_address" {
  type        = string
  description = "Static IP with CIDR"
}

variable "gateway" {
  type = string
}

variable "ssh_public_key" {
  type = string
}

variable "clone_template_id" {
  type        = number
  default     = 9000
  description = "VM template ID to clone from"
}

variable "nameserver" {
  type        = string
  description = "DNS server IP"
}

variable "tags" {
  type    = list(string)
  default = []
}

variable "pci_mappings" {
  type        = list(string)
  default     = []
  description = "List of Proxmox PCI resource mapping names to pass through"
}

variable "onboot" {
  type    = bool
  default = true
}

variable "started" {
  type    = bool
  default = true
}
