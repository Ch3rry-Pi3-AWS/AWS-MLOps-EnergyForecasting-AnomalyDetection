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
  # As with the forecast endpoint, the actual deployment action stays outside
  # Terraform because we want to resolve the latest approved anomaly package at
  # runtime rather than pinning a moving package version in state.
  endpoint_name             = var.endpoint_name != null ? var.endpoint_name : "${var.deployment_name}-anomaly-endpoint"
  model_name_base           = var.model_name_base != null ? var.model_name_base : "${var.deployment_name}-anomaly-model"
  endpoint_config_name_base = var.endpoint_config_name_base != null ? var.endpoint_config_name_base : "${var.deployment_name}-anomaly-endpoint-config"
}
