terraform {
  required_version = ">= 1.5"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

locals {
  # Generate the default bucket names centrally so a caller can override
  # individual names without changing the loop-based resource structure.
  bucket_names = {
    lakehouse  = var.lakehouse_bucket_name != null ? var.lakehouse_bucket_name : "dl-${var.deployment_name}"
    artefacts  = var.artefact_bucket_name != null ? var.artefact_bucket_name : "mlops-artifacts-${var.deployment_name}"
    monitoring = var.monitoring_bucket_name != null ? var.monitoring_bucket_name : "monitoring-${var.deployment_name}"
  }
}

# Create the main storage buckets for data, model artefacts, and operational
# monitoring outputs. `for_each` keeps the configuration compact while still
# producing distinct resources.
resource "aws_s3_bucket" "buckets" {
  for_each = local.bucket_names

  bucket        = each.value
  force_destroy = var.force_destroy

  tags = merge(
    var.tags,
    {
      Name       = each.value
      DataDomain = each.key
    }
  )
}

# Enable bucket versioning across the board so accidental overwrites or
# deletes are easier to recover from during development.
resource "aws_s3_bucket_versioning" "buckets" {
  for_each = aws_s3_bucket.buckets

  bucket = each.value.id

  versioning_configuration {
    status = "Enabled"
  }
}

# Enforce KMS-backed encryption by default on all buckets so later services
# do not need to remember to request encryption on every write path.
resource "aws_s3_bucket_server_side_encryption_configuration" "buckets" {
  for_each = aws_s3_bucket.buckets

  bucket = each.value.id

  rule {
    bucket_key_enabled = true

    apply_server_side_encryption_by_default {
      kms_master_key_id = var.kms_key_arn
      sse_algorithm     = "aws:kms"
    }
  }
}

# Block all public exposure paths. Data-platform buckets should start from a
# private-by-default stance rather than relying on human discipline later.
resource "aws_s3_bucket_public_access_block" "buckets" {
  for_each = aws_s3_bucket.buckets

  bucket                  = each.value.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Seed the lakehouse bucket with the initial Bronze/Silver/Gold-style
# prefixes so the structure is visible and predictable from the outset.
resource "aws_s3_object" "lakehouse_prefixes" {
  for_each = var.create_lakehouse_prefixes ? toset(var.lakehouse_prefixes) : toset([])

  bucket                 = aws_s3_bucket.buckets["lakehouse"].id
  key                    = "${each.value}/"
  content                = ""
  server_side_encryption = "aws:kms"
  kms_key_id             = var.kms_key_arn
  content_type           = "application/x-directory"
}
