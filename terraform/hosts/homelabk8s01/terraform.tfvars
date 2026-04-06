proxmox_endpoint = "https://192.168.10.2:8006"
target_node      = "homelabpve01"

clone_template_id = 9000
ssh_public_key    = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIJfcTkmi2Wd832gavFsAGSLIUN7lrbCX0hWsb/V1mHVg kseneker@MY9RL0MMWJ"

gateway    = "192.168.10.1"
nameserver = "192.168.10.1"

nodes = {
  homelabk8s01-node-1 = {
    role   = "control-plane"
    ip     = "192.168.10.50/24"
    vm_id  = 200
    cores  = 2
    memory = 8192
  }
  homelabk8s01-node-2 = {
    role      = "worker"
    ip        = "192.168.10.51/24"
    vm_id     = 201
    cores     = 4
    memory    = 24576
    disk_size = 64
  }
  homelabk8s01-node-3 = {
    role         = "worker"
    ip           = "192.168.10.52/24"
    vm_id        = 202
    cores        = 4
    memory       = 24576
    disk_size    = 64
    tags         = ["gpu"]
    pci_mappings = ["igpu"]
  }
}
