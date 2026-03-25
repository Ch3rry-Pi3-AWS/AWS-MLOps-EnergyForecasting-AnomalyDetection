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
  # Keep the registry group names readable and deterministic so later training
  # and approval workflows can reference them without guessing resource names.
  forecast_group_name = var.forecast_group_name != null ? var.forecast_group_name : "${var.deployment_name}-forecast-registry"
  anomaly_group_name  = var.anomaly_group_name != null ? var.anomaly_group_name : "${var.deployment_name}-anomaly-registry"
}

# Create a dedicated model package group for forecasting models so later
# training runs can register versioned model packages into a stable registry.
resource "aws_sagemaker_model_package_group" "forecast" {
  model_package_group_name        = local.forecast_group_name
  model_package_group_description = var.forecast_group_description

  tags = merge(
    var.tags,
    {
      Name        = local.forecast_group_name
      ModelFamily = "forecast"
      Component   = "sagemaker-model-registry"
    }
  )
}

# Keep anomaly models in a separate registry group so forecasting and anomaly
# approval flows can evolve independently.
resource "aws_sagemaker_model_package_group" "anomaly" {
  model_package_group_name        = local.anomaly_group_name
  model_package_group_description = var.anomaly_group_description

  tags = merge(
    var.tags,
    {
      Name        = local.anomaly_group_name
      ModelFamily = "anomaly"
      Component   = "sagemaker-model-registry"
    }
  )
}
