locals {
  firewall_enabled = length(var.firewall_ipfilter_cidrs) > 0
}

resource "proxmox_virtual_environment_vm" "vm" {
  name      = var.vm_name
  node_name = var.target_node
  vm_id     = var.vm_id
  tags      = var.tags
  on_boot   = var.onboot
  started   = var.started

  clone {
    vm_id = var.clone_template_id
  }

  cpu {
    cores = var.cores
    type  = "host"
  }

  memory {
    dedicated = var.memory
  }

  agent {
    enabled = var.agent_enabled
  }

  disk {
    datastore_id = var.disk_storage
    interface    = "scsi0"
    size         = var.disk_size
    discard      = "on"
    ssd          = true
  }

  network_device {
    bridge   = var.bridge
    model    = "virtio"
    vlan_id  = var.vlan_id
    firewall = local.firewall_enabled
  }

  vga {
    type = "std"
  }

  dynamic "hostpci" {
    for_each = var.pci_mappings
    content {
      device  = "hostpci${hostpci.key}"
      mapping = hostpci.value
    }
  }

  initialization {
    ip_config {
      ipv4 {
        address = var.ip_address
        gateway = var.gateway
      }
    }

    dns {
      servers = [var.nameserver]
    }

    user_account {
      username = var.username
      keys     = [var.ssh_public_key]
    }
  }
}

# Anti-spoofing only (ADR-016): the NIC may send only from these addresses, plus
# its MAC-derived IPv6 link-local address. The set must exist before ipfilter
# is enabled, or the VM's IPv4 traffic is dropped.
resource "proxmox_virtual_environment_firewall_ipset" "ipfilter_net0" {
  count = local.firewall_enabled ? 1 : 0

  node_name = var.target_node
  vm_id     = proxmox_virtual_environment_vm.vm.vm_id
  name      = "ipfilter-net0"
  comment   = "Managed by Terraform"

  dynamic "cidr" {
    for_each = var.firewall_ipfilter_cidrs
    content {
      name = cidr.value
    }
  }
}

# Policies stay ACCEPT so the firewall drops spoofed sources without filtering
# ports. Proxmox defaults the VM input policy to DROP, which would cut the node off.
resource "proxmox_virtual_environment_firewall_options" "vm" {
  count = local.firewall_enabled ? 1 : 0

  node_name = var.target_node
  vm_id     = proxmox_virtual_environment_vm.vm.vm_id

  enabled       = true
  ipfilter      = true
  macfilter     = var.firewall_macfilter
  input_policy  = "ACCEPT"
  output_policy = "ACCEPT"
  dhcp          = false
  ndp           = true
  radv          = false

  depends_on = [proxmox_virtual_environment_firewall_ipset.ipfilter_net0]
}
