packer {
  required_plugins {
    proxmox = {
      version = ">= 1.2.3"
      source  = "github.com/hashicorp/proxmox"
    }
    ansible = {
      version = ">= 1.1.4"
      source  = "github.com/hashicorp/ansible"
    }
  }
}

source "proxmox-iso" "k8s-node" {
  proxmox_url              = var.proxmox_url
  username                 = var.proxmox_api_token_id
  token                    = var.proxmox_api_token_secret
  insecure_skip_tls_verify = true
  node                     = var.proxmox_node

  vm_id                = var.template_id
  vm_name              = "k8s-node-template"
  template_description = "K8s-ready Ubuntu 24.04 - built by Packer on ${timestamp()}"
  os                   = "l26"
  cpu_type             = "host"
  cores                = 2
  memory               = 4096
  scsi_controller      = "virtio-scsi-single"
  qemu_agent           = true

  boot_iso {
    iso_url          = var.iso_url
    iso_checksum     = var.iso_checksum
    iso_storage_pool = var.iso_storage_pool
    unmount          = true
    type             = "scsi"
  }

  disks {
    storage_pool = var.disk_storage_pool
    disk_size    = "32G"
    type         = "scsi"
    discard      = true
    ssd          = true
    io_thread    = true
  }

  network_adapters {
    bridge = "vmbr0"
    model  = "virtio"
  }

  cloud_init              = true
  cloud_init_storage_pool = var.disk_storage_pool

  http_directory = "http"
  boot_wait      = "5s"
  boot_command = [
    "c",
    "linux /casper/vmlinuz --- autoinstall ds='nocloud-net;s=http://{{ .HTTPIP }}:{{ .HTTPPort }}/' ",
    "<enter><wait>",
    "initrd /casper/initrd ",
    "<enter><wait>",
    "boot",
    "<enter>"
  ]

  ssh_username = "media"
  ssh_password = "packer"
  ssh_timeout  = "20m"
}

build {
  sources = ["source.proxmox-iso.k8s-node"]

  provisioner "ansible" {
    playbook_file = "playbook.yml"
    roles_path    = "../../ansible/roles"
    extra_arguments = [
      "--extra-vars", "k8s_prereqs_version=${var.k8s_version}",
      "--extra-vars", "k8s_prereqs_version_minor=${var.k8s_version_minor}",
      "--extra-vars", "base_timezone=${var.timezone}",
      "--extra-vars", "base_media_uid=${var.media_uid}",
      "--extra-vars", "base_media_gid=${var.media_gid}",
    ]
  }
}
