module "vm" {
  for_each = var.nodes
  source   = "../../modules/proxmox-vm"

  vm_name           = each.key
  vm_id             = each.value.vm_id
  target_node       = var.target_node
  cores             = each.value.cores
  memory            = each.value.memory
  disk_size         = each.value.disk_size
  ip_address        = each.value.ip
  gateway           = var.gateway
  ssh_public_key    = var.ssh_public_key
  clone_template_id = var.clone_template_id
  nameserver        = var.nameserver
  bridge            = var.bridge
  username          = var.username
  agent_enabled     = var.agent_enabled
  onboot            = var.onboot
  tags              = concat(var.tags, [each.value.role], each.value.tags)
  pci_mappings      = each.value.pci_mappings

  # ADR-016 hypervisor enforcement: an access-port NIC and anti-spoofing filters.
  vlan_id                 = var.nic_vlan_id
  firewall_ipfilter_cidrs = length(var.l2_pool_cidrs) > 0 ? concat([split("/", each.value.ip)[0]], var.l2_pool_cidrs) : []
  firewall_vxlan_peers    = [for n in values(var.nodes) : split("/", n.ip)[0]]

  # ADR-028: workers carry a VLAN 20 NIC for Multus attachments, and macvlan's
  # extra MACs need Proxmox MAC filtering off; the per-NIC IP filters still apply.
  firewall_macfilter = !(var.iot_nic != null && each.value.role == "worker")
  iot_nic = var.iot_nic != null && each.value.role == "worker" ? {
    vlan_id   = var.iot_nic.vlan_id
    subnet    = var.iot_nic.subnet
    addresses = [for a in var.iot_nic.attachments : a.address]
    tcp_ports = distinct(flatten([for a in var.iot_nic.attachments : a.tcp_ports]))
    udp_ports = distinct(flatten([for a in var.iot_nic.attachments : a.udp_ports]))
  } : null
}
