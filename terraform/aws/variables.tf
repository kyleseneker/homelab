variable "aws_region" {
  type        = string
  description = "AWS region where the KMS key will be created"
  default     = "us-east-1"
}

variable "environment" {
  type        = string
  description = "Environment label applied to resource tags"
  default     = "homelab"
}

variable "key_alias" {
  type        = string
  description = "KMS key alias (without the alias/ prefix)"
  default     = "vault-unseal"
}

variable "household_domain" {
  type        = string
  description = "Household domain registered in Route 53; homelab services are served under it"
  default     = "seneker.io"
}

variable "homelab_subdomain" {
  type        = string
  description = "Subdomain of the household domain that holds internal-only homelab service names"
  default     = "home"
}
