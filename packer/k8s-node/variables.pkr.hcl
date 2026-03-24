variable "proxmox_url" {
  type        = string
  description = "Proxmox API URL (e.g. https://192.168.10.2:8006/api2/json)"
}

variable "proxmox_api_token_id" {
  type        = string
  description = "Proxmox API token ID (e.g. terraform@pam!terraform)"
}

variable "proxmox_api_token_secret" {
  type        = string
  sensitive   = true
  description = "Proxmox API token secret"
}

variable "proxmox_node" {
  type        = string
  description = "Proxmox node to build the template on"
}

variable "template_id" {
  type        = number
  default     = 9000
  description = "VM ID for the resulting template"
}

variable "iso_url" {
  type        = string
  default     = "https://releases.ubuntu.com/noble/ubuntu-24.04.2-live-server-amd64.iso"
  description = "Ubuntu server ISO download URL"
}

variable "iso_checksum" {
  type        = string
  default     = "file:https://releases.ubuntu.com/noble/SHA256SUMS"
  description = "ISO checksum or file URL for automatic verification"
}

variable "iso_storage_pool" {
  type        = string
  default     = "local"
  description = "Proxmox storage pool for the ISO"
}

variable "disk_storage_pool" {
  type        = string
  default     = "local-lvm"
  description = "Proxmox storage pool for the VM disk and cloud-init drive"
}

variable "k8s_version" {
  type        = string
  default     = "1.31.4"
  description = "Full Kubernetes version to install (e.g. 1.31.4)"
}

variable "k8s_version_minor" {
  type        = string
  default     = "1.31"
  description = "Kubernetes minor version for apt repository (e.g. 1.31)"
}

variable "timezone" {
  type        = string
  default     = "America/Chicago"
  description = "Timezone for the template"
}

variable "media_uid" {
  type        = number
  default     = 977
  description = "UID for the shared media user"
}

variable "media_gid" {
  type        = number
  default     = 988
  description = "GID for the shared media group"
}
