terraform {
  required_version = ">= 1.5.0"

  cloud {
    organization = "kyleseneker"

    workspaces {
      name = "homelab-aws"
    }
  }

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.0.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

# Customer-managed KMS key for Vault auto-unseal
resource "aws_kms_key" "vault_unseal" {
  description             = "Vault auto-unseal key for ${var.environment}"
  deletion_window_in_days = 30
  enable_key_rotation     = true

  lifecycle {
    prevent_destroy = true
  }

  tags = {
    Name        = "vault-unseal-${var.environment}"
    Environment = var.environment
    ManagedBy   = "terraform"
  }
}

resource "aws_kms_alias" "vault_unseal" {
  name          = "alias/${var.key_alias}-${var.environment}"
  target_key_id = aws_kms_key.vault_unseal.key_id
}

# Dedicated IAM user with no console access
resource "aws_iam_user" "vault_unseal" {
  name = "vault-unseal-${var.environment}"

  tags = {
    Environment = var.environment
    ManagedBy   = "terraform"
  }
}

resource "aws_iam_access_key" "vault_unseal" {
  user = aws_iam_user.vault_unseal.name
}

# Minimal policy — only the three actions Vault's awskms seal needs
data "aws_iam_policy_document" "vault_unseal" {
  statement {
    sid    = "VaultKMSUnseal"
    effect = "Allow"

    actions = [
      "kms:Encrypt",
      "kms:Decrypt",
      "kms:DescribeKey",
    ]

    resources = [aws_kms_key.vault_unseal.arn]
  }
}

resource "aws_iam_policy" "vault_unseal" {
  name        = "vault-unseal-${var.environment}"
  description = "Minimal KMS permissions for Vault auto-unseal"
  policy      = data.aws_iam_policy_document.vault_unseal.json
}

resource "aws_iam_user_policy_attachment" "vault_unseal" {
  user       = aws_iam_user.vault_unseal.name
  policy_arn = aws_iam_policy.vault_unseal.arn
}

# S3 bucket for offsite Velero backups
resource "aws_s3_bucket" "velero_offsite" {
  bucket = "velero-offsite-${var.environment}"

  lifecycle {
    prevent_destroy = true
  }

  tags = {
    Name        = "velero-offsite-${var.environment}"
    Environment = var.environment
    ManagedBy   = "terraform"
  }
}

resource "aws_s3_bucket_versioning" "velero_offsite" {
  bucket = aws_s3_bucket.velero_offsite.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "velero_offsite" {
  bucket = aws_s3_bucket.velero_offsite.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "velero_offsite" {
  bucket = aws_s3_bucket.velero_offsite.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

data "aws_iam_policy_document" "velero_offsite_transport" {
  statement {
    sid    = "DenyInsecureTransport"
    effect = "Deny"
    principals {
      type        = "*"
      identifiers = ["*"]
    }
    actions = ["s3:*"]
    resources = [
      aws_s3_bucket.velero_offsite.arn,
      "${aws_s3_bucket.velero_offsite.arn}/*",
    ]
    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["false"]
    }
  }
}

resource "aws_s3_bucket_policy" "velero_offsite" {
  bucket = aws_s3_bucket.velero_offsite.id
  policy = data.aws_iam_policy_document.velero_offsite_transport.json
}

resource "aws_s3_bucket_lifecycle_configuration" "velero_offsite" {
  bucket = aws_s3_bucket.velero_offsite.id

  rule {
    id     = "expire-vault-raft-snapshots"
    status = "Enabled"
    filter {
      prefix = "vault-raft-snapshots/"
    }
    expiration {
      days = 30
    }
  }

  rule {
    id     = "transition-to-ia"
    status = "Enabled"
    filter {}

    transition {
      days          = 30
      storage_class = "STANDARD_IA"
    }

    noncurrent_version_expiration {
      noncurrent_days = 90
    }
  }
}

# Dedicated IAM user for Velero offsite backups
resource "aws_iam_user" "velero_offsite" {
  name = "velero-offsite-${var.environment}"

  tags = {
    Environment = var.environment
    ManagedBy   = "terraform"
  }
}

resource "aws_iam_access_key" "velero_offsite" {
  user = aws_iam_user.velero_offsite.name
}

data "aws_iam_policy_document" "velero_offsite" {
  statement {
    sid    = "VeleroS3Access"
    effect = "Allow"

    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:DeleteObject",
      "s3:ListBucket",
      "s3:GetBucketLocation",
    ]

    resources = [
      aws_s3_bucket.velero_offsite.arn,
      "${aws_s3_bucket.velero_offsite.arn}/*",
    ]
  }
}

resource "aws_iam_policy" "velero_offsite" {
  name        = "velero-offsite-${var.environment}"
  description = "Minimal S3 permissions for Velero offsite backups"
  policy      = data.aws_iam_policy_document.velero_offsite.json
}

resource "aws_iam_user_policy_attachment" "velero_offsite" {
  user       = aws_iam_user.velero_offsite.name
  policy_arn = aws_iam_policy.velero_offsite.arn
}

# Household domain, registered through the Route 53 console and adopted here.
# Terraform never registers or deletes it: destroy only removes it from state.
resource "aws_route53domains_registered_domain" "household" {
  domain_name = var.household_domain

  auto_renew         = true
  transfer_lock      = true
  admin_privacy      = true
  registrant_privacy = true
  tech_privacy       = true

  dynamic "name_server" {
    for_each = aws_route53_zone.household.name_servers
    content {
      name = name_server.value
    }
  }

  tags = {
    Environment = var.environment
    ManagedBy   = "terraform"
  }
}

# Public hosted zone created by the registration. Homelab service records stay
# in the UniFi gateway's local DNS; this zone only carries ACME challenges and
# anything deliberately public.
resource "aws_route53_zone" "household" {
  name    = var.household_domain
  comment = "Household domain; homelab records are internal-only"

  lifecycle {
    prevent_destroy = true
  }

  tags = {
    Environment = var.environment
    ManagedBy   = "terraform"
  }
}

# Dedicated IAM user for cert-manager's ACME DNS-01 challenges
resource "aws_iam_user" "cert_manager_dns01" {
  name = "cert-manager-dns01-${var.environment}"

  tags = {
    Environment = var.environment
    ManagedBy   = "terraform"
  }
}

resource "aws_iam_access_key" "cert_manager_dns01" {
  user = aws_iam_user.cert_manager_dns01.name
}

# Only the TXT record ACME validates for the homelab wildcard certificate
# (*.home.<domain>); public records elsewhere in the zone stay out of reach of a
# compromised cluster. The ClusterIssuer
# names the zone ID, so no zone lookup permission is needed.
data "aws_iam_policy_document" "cert_manager_dns01" {
  statement {
    sid       = "ReadChangeStatus"
    effect    = "Allow"
    actions   = ["route53:GetChange"]
    resources = ["arn:aws:route53:::change/*"]
  }

  statement {
    sid       = "ListZoneRecords"
    effect    = "Allow"
    actions   = ["route53:ListResourceRecordSets"]
    resources = [aws_route53_zone.household.arn]
  }

  statement {
    sid       = "WriteChallengeRecord"
    effect    = "Allow"
    actions   = ["route53:ChangeResourceRecordSets"]
    resources = [aws_route53_zone.household.arn]

    condition {
      test     = "ForAllValues:StringEquals"
      variable = "route53:ChangeResourceRecordSetsNormalizedRecordNames"
      values   = ["_acme-challenge.${var.homelab_subdomain}.${var.household_domain}"]
    }

    condition {
      test     = "ForAllValues:StringEquals"
      variable = "route53:ChangeResourceRecordSetsRecordTypes"
      values   = ["TXT"]
    }
  }
}

resource "aws_iam_policy" "cert_manager_dns01" {
  name        = "cert-manager-dns01-${var.environment}"
  description = "cert-manager ACME DNS-01: the homelab challenge TXT record only"
  policy      = data.aws_iam_policy_document.cert_manager_dns01.json
}

resource "aws_iam_user_policy_attachment" "cert_manager_dns01" {
  user       = aws_iam_user.cert_manager_dns01.name
  policy_arn = aws_iam_policy.cert_manager_dns01.arn
}
