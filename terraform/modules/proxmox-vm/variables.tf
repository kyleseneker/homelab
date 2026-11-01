variable "vm_name" {
  type = string
}

variable "bridge" {
  type    = string
  default = "vmbr0"
}

variable "username" {
  type    = string
  default = "media"
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

variable "agent_enabled" {
  type    = bool
  default = true
}

variable "vlan_id" {
  type        = number
  default     = null
  description = "VLAN tag for the NIC. Set only on a VLAN-aware bridge, where 1 makes an access port on the untagged native VLAN"
}

variable "firewall_ipfilter_cidrs" {
  type        = list(string)
  default     = []
  description = "Source addresses the NIC may send from (ipfilter-net0). Empty leaves the Proxmox VM firewall off"
}

variable "firewall_macfilter" {
  type        = bool
  default     = true
  description = "Proxmox MAC filtering, a per-VM option; disable for VMs whose NICs carry macvlan child MACs"
}

variable "firewall_vxlan_peers" {
  type        = list(string)
  default     = []
  description = "Node addresses that may send Cilium VXLAN (UDP 8472) to the VM; other sources are dropped. Empty leaves the port unfiltered. Needs the VM firewall"
}
