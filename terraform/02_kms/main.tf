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

data "aws_caller_identity" "current" {}

data "aws_partition" "current" {}

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

resource "aws_kms_alias" "main" {
  name          = local.alias_name
  target_key_id = aws_kms_key.main.key_id
}

