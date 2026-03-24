# Expose bucket names and ARNs so downstream IAM and compute modules can
# reference the storage layer without hardcoding values.
output "lakehouse_bucket_name" {
  value = aws_s3_bucket.buckets["lakehouse"].bucket
}

output "lakehouse_bucket_arn" {
  value = aws_s3_bucket.buckets["lakehouse"].arn
}

output "artefact_bucket_name" {
  value = aws_s3_bucket.buckets["artefacts"].bucket
}

output "artefact_bucket_arn" {
  value = aws_s3_bucket.buckets["artefacts"].arn
}

output "monitoring_bucket_name" {
  value = aws_s3_bucket.buckets["monitoring"].bucket
}

output "monitoring_bucket_arn" {
  value = aws_s3_bucket.buckets["monitoring"].arn
}
