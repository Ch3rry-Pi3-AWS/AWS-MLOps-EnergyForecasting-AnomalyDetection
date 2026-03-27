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
  tracking_server_name = var.tracking_server_name != null ? var.tracking_server_name : "${var.deployment_name}-mlflow-tracking"
  artifact_store_uri   = "s3://${var.artefact_bucket_name}/${trim(var.artifact_store_prefix, "/")}/"
}

resource "aws_sagemaker_mlflow_tracking_server" "this" {
  tracking_server_name            = local.tracking_server_name
  artifact_store_uri              = local.artifact_store_uri
  role_arn                        = var.sagemaker_role_arn
  automatic_model_registration    = var.automatic_model_registration
  mlflow_version                  = var.mlflow_version
  tracking_server_size            = var.tracking_server_size
  weekly_maintenance_window_start = var.weekly_maintenance_window_start
  tags                            = var.tags
}
