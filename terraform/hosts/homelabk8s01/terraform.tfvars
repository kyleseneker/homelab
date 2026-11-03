proxmox_endpoint = "https://192.168.10.2:8006"
target_node      = "homelabpve01"

clone_template_id = 9000
ssh_public_key    = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIJfcTkmi2Wd832gavFsAGSLIUN7lrbCX0hWsb/V1mHVg kseneker@MY9RL0MMWJ"

gateway    = "192.168.10.1"
nameserver = "192.168.10.1"

# ADR-016: vmbr0 is VLAN-aware, so each node NIC is an access port on the native VLAN.
nic_vlan_id = 1

# ADR-028: each worker's second NIC is an access port on the IoT VLAN. Record
# every Multus attachment here; its address is the only source the NIC may send
# from, and its ports are the only ones open from the IoT subnet.
iot_nic = {
  vlan_id = 20
  subnet  = "192.168.20.0/24"
  attachments = [
    # Home Assistant (ADR-029). No device-initiated ports yet; add each
    # integration's ports here and to docs/apps/home-assistant.md.
    { name = "home-assistant", address = "192.168.20.10" },
  ]
}

# ADR-016 anti-spoofing: each NIC may send only from its node address and the
# Cilium L2 LoadBalancer pool (192.168.10.200 -- .250).
l2_pool_cidrs = [
  "192.168.10.200/29",
  "192.168.10.208/28",
  "192.168.10.224/28",
  "192.168.10.240/29",
  "192.168.10.248/31",
  "192.168.10.250/32",
]

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
    memory    = 16384
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
