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
  # Keep evaluation reports in the shared artefact bucket so they sit next to
  # training outputs and model-registration artefacts rather than creating yet
  # another storage location for the same lifecycle.
  forecast_report_prefix = var.forecast_report_prefix != null ? trim(var.forecast_report_prefix, "/") : "sagemaker/model_evaluation/forecast"
  anomaly_report_prefix  = var.anomaly_report_prefix != null ? trim(var.anomaly_report_prefix, "/") : "sagemaker/model_evaluation/anomaly"

  forecast_report_s3_uri = "s3://${var.artefact_bucket_name}/${local.forecast_report_prefix}/"
  anomaly_report_s3_uri  = "s3://${var.artefact_bucket_name}/${local.anomaly_report_prefix}/"
}
