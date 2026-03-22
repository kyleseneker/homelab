output "control_plane_ip" {
  value = split("/", [
    for k, v in var.nodes : module.vm[k].ip_address if v.role == "control-plane"
  ][0])[0]
}

output "node_ips" {
  value = { for k, v in var.nodes : k => split("/", module.vm[k].ip_address)[0] }
}

output "vm_ids" {
  value = { for k, v in var.nodes : k => module.vm[k].vm_id }
}
