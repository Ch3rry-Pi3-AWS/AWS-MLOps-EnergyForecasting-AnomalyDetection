terraform {
  required_version = ">= 1.5"

  required_providers {
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }
}

# Generate one shared animal-style suffix for the whole deployment so later
# resources can reuse a consistent naming seed rather than inventing their
# own unrelated random names.
resource "random_pet" "stack" {
  length    = 2
  separator = "-"
}

locals {
  # Build the core deployment identifier consumed by later modules.
  deployment_name = "${var.resource_prefix}-${var.environment}-${random_pet.stack.id}"

  # Keep the common tag set centralised here so downstream modules can apply
  # consistent metadata without duplicating the same map repeatedly.
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
