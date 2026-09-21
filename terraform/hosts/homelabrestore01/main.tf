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
}
