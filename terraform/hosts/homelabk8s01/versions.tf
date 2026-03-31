terraform {
  required_version = ">= 1.5.0"

  cloud {
    organization = "kyleseneker"

    workspaces {
      name = "homelab-homelabk8s01"
    }
  }

  required_providers {
    proxmox = {
      source  = "bpg/proxmox"
      version = ">= 0.66.0"
    }
  }
}
