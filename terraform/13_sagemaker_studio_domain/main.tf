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

# If the caller does not provide explicit networking, fall back to the default
# VPC so the Studio domain stays easy to spin up in a portfolio account.
data "aws_vpc" "default" {
  count   = var.vpc_id == null ? 1 : 0
  default = true
}

data "aws_subnets" "default" {
  count = var.subnet_ids == null ? 1 : 0

  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default[0].id]
  }
}

locals {
  # Keep Studio naming deterministic so the domain and user profile are easy to
  # recognise alongside the rest of the deployment's SageMaker resources.
  domain_name       = var.domain_name != null ? var.domain_name : "${var.deployment_name}-studio"
  user_profile_name = var.user_profile_name != null ? var.user_profile_name : "${var.deployment_name}-user"
  resolved_vpc_id   = var.vpc_id != null ? var.vpc_id : data.aws_vpc.default[0].id
  resolved_subnets  = var.subnet_ids != null ? var.subnet_ids : data.aws_subnets.default[0].ids
}

# Create the Studio domain itself so SageMaker resources such as model package
# groups can be browsed through the richer Studio UI rather than only the CLI.
resource "aws_sagemaker_domain" "main" {
  auth_mode               = var.auth_mode
  domain_name             = local.domain_name
  vpc_id                  = local.resolved_vpc_id
  subnet_ids              = local.resolved_subnets
  kms_key_id              = var.kms_key_arn
  app_network_access_type = var.app_network_access_type

  default_user_settings {
    execution_role = var.sagemaker_role_arn
  }

  # Use delete-by-default so the dev stack can be torn down cleanly without
  # leaving the Studio home EFS behind unless the caller opts to retain it.
  retention_policy {
    home_efs_file_system = var.home_efs_retention_mode
  }

  tags = merge(
    var.tags,
    {
      Name      = local.domain_name
      Component = "sagemaker-studio-domain"
    }
  )
}

# Create a first user profile so the domain is usable immediately after deploy.
resource "aws_sagemaker_user_profile" "default" {
  domain_id         = aws_sagemaker_domain.main.id
  user_profile_name = local.user_profile_name

  user_settings {
    execution_role = var.sagemaker_role_arn
  }

  tags = merge(
    var.tags,
    {
      Name      = local.user_profile_name
      Component = "sagemaker-user-profile"
    }
  )
}
