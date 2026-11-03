locals {
  firewall_enabled = length(var.firewall_ipfilter_cidrs) > 0

  # Proxmox stores ipset entries without a /32 suffix and returns them sorted
  # as strings. Matching that form keeps the ordered list stable: a diff would
  # replace the set, briefly leaving ipfilter with no allowed source.
  ipfilter_cidrs = sort([for c in var.firewall_ipfilter_cidrs : trimsuffix(c, "/32")])

  vxlan_filter_enabled = local.firewall_enabled && length(var.firewall_vxlan_peers) > 0
  vxlan_peers          = sort([for c in var.firewall_vxlan_peers : trimsuffix(c, "/32")])

  iot_enabled   = local.firewall_enabled && var.iot_nic != null
  iot_addresses = local.iot_enabled ? sort([for c in var.iot_nic.addresses : trimsuffix(c, "/32")]) : []

  vxlan_rules = local.vxlan_filter_enabled ? [
    { action = "ACCEPT", proto = "udp", dport = "8472", sport = null, source = "+guest/vxlan-peers", iface = null, comment = "Cilium VXLAN from cluster nodes" },
    { action = "DROP", proto = "udp", dport = "8472", sport = null, source = null, iface = null, comment = "Cilium VXLAN from any other source" },
  ] : []

  # Replies to connections the attached pod opens pass the firewall's connection
  # tracking; these admit what IoT devices start.
  iot_rules = local.iot_enabled ? concat(
    [
      { action = "ACCEPT", proto = "udp", dport = "5353", sport = null, source = var.iot_nic.subnet, iface = "net1", comment = "mDNS from IoT devices" },
      { action = "ACCEPT", proto = "udp", dport = "1900", sport = null, source = var.iot_nic.subnet, iface = "net1", comment = "SSDP notifications from IoT devices" },
      { action = "ACCEPT", proto = "udp", dport = null, sport = "1900", source = var.iot_nic.subnet, iface = "net1", comment = "SSDP replies to searches" },
    ],
    [for p in var.iot_nic.tcp_ports : { action = "ACCEPT", proto = "tcp", dport = tostring(p), sport = null, source = var.iot_nic.subnet, iface = "net1", comment = "Attached workload port" }],
    [for p in var.iot_nic.udp_ports : { action = "ACCEPT", proto = "udp", dport = tostring(p), sport = null, source = var.iot_nic.subnet, iface = "net1", comment = "Attached workload port" }],
    [{ action = "DROP", proto = null, dport = null, sport = null, source = null, iface = "net1", comment = "Everything else from the IoT VLAN" }],
  ) : []

  vm_rules = concat(local.vxlan_rules, local.iot_rules)
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

  dynamic "network_device" {
    for_each = local.iot_enabled ? [var.iot_nic] : []
    content {
      bridge   = var.bridge
      model    = "virtio"
      vlan_id  = network_device.value.vlan_id
      firewall = true
    }
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
    for_each = local.ipfilter_cidrs
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

  depends_on = [
    proxmox_virtual_environment_firewall_ipset.ipfilter_net0,
    proxmox_virtual_environment_firewall_ipset.ipfilter_net1,
  ]
}

# The IoT NIC may send only from its attachments' addresses. Until a workload
# is attached the set is empty, so the NIC sends nothing.
resource "proxmox_virtual_environment_firewall_ipset" "ipfilter_net1" {
  count = local.iot_enabled ? 1 : 0

  node_name = var.target_node
  vm_id     = proxmox_virtual_environment_vm.vm.vm_id
  name      = "ipfilter-net1"
  comment   = "Managed by Terraform"

  dynamic "cidr" {
    for_each = local.iot_addresses
    content {
      name = cidr.value
    }
  }
}

# Cilium's VXLAN overlay is unauthenticated: a packet that reaches UDP 8472 is
# delivered into the pod network, past network policy. Only the cluster's nodes
# may send it.
resource "proxmox_virtual_environment_firewall_ipset" "vxlan_peers" {
  count = local.vxlan_filter_enabled ? 1 : 0

  node_name = var.target_node
  vm_id     = proxmox_virtual_environment_vm.vm.vm_id
  name      = "vxlan-peers"
  comment   = "Managed by Terraform"

  dynamic "cidr" {
    for_each = local.vxlan_peers
    content {
      name = cidr.value
    }
  }
}

resource "proxmox_virtual_environment_firewall_rules" "vm" {
  count = length(local.vm_rules) > 0 ? 1 : 0

  node_name = var.target_node
  vm_id     = proxmox_virtual_environment_vm.vm.vm_id

  dynamic "rule" {
    for_each = local.vm_rules
    content {
      type    = "in"
      action  = rule.value.action
      proto   = rule.value.proto
      dport   = rule.value.dport
      sport   = rule.value.sport
      source  = rule.value.source
      iface   = rule.value.iface
      comment = rule.value.comment
    }
  }

  depends_on = [proxmox_virtual_environment_firewall_ipset.vxlan_peers]
}
