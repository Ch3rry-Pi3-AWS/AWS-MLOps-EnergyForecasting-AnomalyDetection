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
  # The actual endpoint deployment is handled by a local runner because model
  # package selection is an operational action: we want to resolve the latest
  # approved package at deployment time rather than baking a moving target into
  # Terraform state.
  endpoint_name             = var.endpoint_name != null ? var.endpoint_name : "${var.deployment_name}-forecast-endpoint"
  model_name_base           = var.model_name_base != null ? var.model_name_base : "${var.deployment_name}-forecast-model"
  endpoint_config_name_base = var.endpoint_config_name_base != null ? var.endpoint_config_name_base : "${var.deployment_name}-forecast-endpoint-config"
}
