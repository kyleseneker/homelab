output "control_plane_ip" {
  description = "IP address of the control plane node (without CIDR suffix)"
  value = try(split("/", [
    for k, v in var.nodes : module.vm[k].ip_address if v.role == "control-plane"
  ][0])[0], null)
}

output "node_ips" {
  description = "Map of node names to their IP addresses"
  value       = { for k, v in var.nodes : k => split("/", module.vm[k].ip_address)[0] }
}

output "vm_ids" {
  description = "Map of node names to their Proxmox VM IDs"
  value       = { for k, v in var.nodes : k => module.vm[k].vm_id }
}
