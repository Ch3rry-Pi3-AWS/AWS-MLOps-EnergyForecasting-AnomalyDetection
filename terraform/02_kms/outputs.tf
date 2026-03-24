# Surface the core KMS identifiers so later modules can use the key for S3,
# Lambda, and other encrypted resources.
output "kms_key_id" {
  value = aws_kms_key.main.key_id
}

output "kms_key_arn" {
  value = aws_kms_key.main.arn
}

output "kms_alias_name" {
  value = aws_kms_alias.main.name
}
