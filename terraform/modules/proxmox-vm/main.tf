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
    enabled = true
  }

  disk {
    datastore_id = var.disk_storage
    interface    = "scsi0"
    size         = var.disk_size
    discard      = "on"
    ssd          = true
  }

  network_device {
    bridge = "vmbr0"
    model  = "virtio"
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
      username = "media"
      keys     = [var.ssh_public_key]
    }
  }
}
