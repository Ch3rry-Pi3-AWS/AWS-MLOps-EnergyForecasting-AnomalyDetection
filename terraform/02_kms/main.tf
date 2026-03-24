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

# Discover the authenticated AWS account dynamically so the policy does not
# need a hardcoded account ID.
data "aws_caller_identity" "current" {}

# Resolve the AWS partition dynamically in case the module is ever reused in
# GovCloud or another non-standard partition.
data "aws_partition" "current" {}

# Start with a safe baseline key policy that keeps the owning AWS account in
# control of the key. This avoids accidentally creating a key that nobody in
# the account can administer.
data "aws_iam_policy_document" "kms" {
  statement {
    sid       = "EnableRootPermissions"
    effect    = "Allow"
    actions   = ["kms:*"]
    resources = ["*"]

    principals {
      type        = "AWS"
      identifiers = ["arn:${data.aws_partition.current.partition}:iam::${data.aws_caller_identity.current.account_id}:root"]
    }
  }
}

locals {
  # Prefer an explicit alias if one is supplied; otherwise derive a readable
  # alias from the shared deployment name.
  alias_name = var.kms_key_alias_name != null ? var.kms_key_alias_name : "${var.kms_key_alias_prefix}-${var.deployment_name}"
}

resource "aws_kms_key" "main" {
  description             = var.description
  deletion_window_in_days = var.deletion_window_in_days
  enable_key_rotation     = var.enable_key_rotation
  policy                  = data.aws_iam_policy_document.kms.json

  tags = merge(
    var.tags,
    {
      Name = replace(local.alias_name, "alias/", "")
    }
  )
}

# The alias gives humans and downstream configuration a stable, readable
# handle for the key instead of relying on the opaque key ID alone.
resource "aws_kms_alias" "main" {
  name          = local.alias_name
  target_key_id = aws_kms_key.main.key_id
}
