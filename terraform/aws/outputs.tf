output "kms_key_id" {
  description = "KMS key ID"
  value       = aws_kms_key.vault_unseal.key_id
}

output "kms_key_arn" {
  description = "KMS key ARN"
  value       = aws_kms_key.vault_unseal.arn
}

output "kms_key_alias" {
  description = "KMS key alias"
  value       = aws_kms_alias.vault_unseal.name
}

output "iam_user_name" {
  description = "IAM user name"
  value       = aws_iam_user.vault_unseal.name
}

output "aws_access_key_id" {
  description = "AWS access key ID for the vault-unseal IAM user"
  value       = aws_iam_access_key.vault_unseal.id
}

output "aws_secret_access_key" {
  description = "AWS secret access key for the vault-unseal IAM user"
  value       = aws_iam_access_key.vault_unseal.secret
  sensitive   = true
}

output "velero_offsite_bucket_name" {
  description = "S3 bucket name for Velero offsite backups"
  value       = aws_s3_bucket.velero_offsite.id
}

output "velero_offsite_bucket_arn" {
  description = "S3 bucket ARN for Velero offsite backups"
  value       = aws_s3_bucket.velero_offsite.arn
}

output "velero_offsite_access_key_id" {
  description = "AWS access key ID for the velero-offsite IAM user"
  value       = aws_iam_access_key.velero_offsite.id
}

output "velero_offsite_secret_access_key" {
  description = "AWS secret access key for the velero-offsite IAM user"
  value       = aws_iam_access_key.velero_offsite.secret
  sensitive   = true
}
