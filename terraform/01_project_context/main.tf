terraform {
  required_version = ">= 1.5"

  required_providers {
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }
}

resource "random_pet" "stack" {
  length    = 2
  separator = "-"
}

locals {
  deployment_name = "${var.resource_prefix}-${var.environment}-${random_pet.stack.id}"

  standard_tags = merge(
    {
      Project      = var.project_name
      ProjectSlug  = var.project_slug
      Environment  = var.environment
      ManagedBy    = "terraform"
      Repository   = "AWS-MLOps-EnergyForecasting-AnomalyDetection"
      Owner        = var.owner
      CostCentre   = var.cost_centre
      StackSuffix  = random_pet.stack.id
      DeploymentId = local.deployment_name
    },
    var.extra_tags
  )
}

