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
