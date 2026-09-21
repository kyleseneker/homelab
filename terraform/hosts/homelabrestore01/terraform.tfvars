proxmox_endpoint = "https://192.168.10.2:8006"
target_node      = "homelabpve01"

clone_template_id = 9010
ssh_public_key    = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIOmaW09xCiEsBZzDCfoQMEDXOgDEle6VXfuVwmGkrcNR homelabrestore01"

bridge     = "vmbr1"
gateway    = "172.26.0.1"
nameserver = "1.1.1.1"
username   = "labadmin"

# The cloud image does not contain the guest agent before Ansible runs.
agent_enabled = false
onboot        = false
tags          = ["restore-lab", "k8s"]

nodes = {
  homelabrestore01-node-1 = {
    role      = "control-plane"
    ip        = "172.26.0.10/24"
    vm_id     = 300
    cores     = 2
    memory    = 3072
    disk_size = 32
  }
  homelabrestore01-node-2 = {
    role      = "worker"
    ip        = "172.26.0.11/24"
    vm_id     = 301
    cores     = 2
    memory    = 4096
    disk_size = 32
  }
}
