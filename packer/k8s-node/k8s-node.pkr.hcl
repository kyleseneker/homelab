packer {
  required_plugins {
    proxmox = {
      version = "= 1.2.4"
      source  = "github.com/hashicorp/proxmox"
    }
    ansible = {
      version = "= 1.1.6"
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
  vm_name              = var.template_name
  template_description = "K8s-ready Ubuntu 24.04 - built by Packer on ${timestamp()}"
  os                   = "l26"
  cpu_type             = "host"
  cores                = 2
  memory               = 4096
  scsi_controller      = "virtio-scsi-single"
  qemu_agent           = true
  # The default CD boot order selects the non-bootable seed ISO.
  boot = "order=scsi0;scsi1"

  boot_iso {
    iso_url          = var.iso_file == "" ? var.iso_url : null
    iso_file         = var.iso_file
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
    bridge = var.network_bridge
    model  = "virtio"
  }

  cloud_init              = true
  cloud_init_storage_pool = var.disk_storage_pool

  additional_iso_files {
    cd_label = "cidata"
    cd_content = {
      "user-data" = templatefile("http/user-data", {
        media_uid      = var.media_uid
        media_gid      = var.media_gid
        ssh_public_key = var.ssh_public_key
        build_network  = var.build_network
      })
      "meta-data" = file("http/meta-data")
    }
    iso_storage_pool = var.iso_storage_pool
    unmount          = true
  }
  boot_wait = "5s"
  boot_command = [
    "c",
    "linux /casper/vmlinuz autoinstall --- ",
    "<enter><wait>",
    "initrd /casper/initrd ",
    "<enter><wait>",
    "boot",
    "<enter>"
  ]

  ssh_username                 = "media"
  ssh_private_key_file         = var.ssh_private_key_file
  ssh_bastion_host             = var.ssh_bastion_host
  ssh_bastion_username         = var.ssh_bastion_username
  ssh_bastion_private_key_file = var.ssh_bastion_private_key_file
  ssh_timeout                  = "20m"
}

build {
  sources = ["source.proxmox-iso.k8s-node"]

  provisioner "ansible" {
    playbook_file = "playbook.yml"
    ansible_env_vars = [
      "ANSIBLE_ROLES_PATH=${abspath("../../ansible/roles")}",
    ]
    extra_arguments = [
      "--extra-vars", "k8s_prereqs_version=${var.k8s_version}",
      "--extra-vars", "k8s_prereqs_version_minor=${var.k8s_version_minor}",
      "--extra-vars", "base_timezone=${var.timezone}",
      "--extra-vars", "base_media_uid=${var.media_uid}",
      "--extra-vars", "base_media_gid=${var.media_gid}",
    ]
  }
}
