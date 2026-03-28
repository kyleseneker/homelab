terraform {
  required_version = ">= 1.5.0"

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

resource "aws_s3_bucket_lifecycle_configuration" "velero_offsite" {
  bucket = aws_s3_bucket.velero_offsite.id

  rule {
    id     = "transition-to-ia"
    status = "Enabled"

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
