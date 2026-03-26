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
  gold_input_s3_uri            = "s3://${var.lakehouse_bucket_name}/${trim(var.gold_forecast_features_prefix, "/")}/"
  prepared_input_s3_uri        = "s3://${var.artefact_bucket_name}/${trim(var.prepared_input_prefix, "/")}/"
  training_output_s3_uri       = "s3://${var.artefact_bucket_name}/${trim(var.training_output_prefix, "/")}/"
  evaluation_output_s3_uri     = "s3://${var.artefact_bucket_name}/${trim(var.evaluation_output_prefix, "/")}/"
  job_base_name                = var.job_base_name != null ? var.job_base_name : "${var.deployment_name}-forecast-deepar-train"
  temporary_model_base_name    = "${var.deployment_name}-forecast-deepar-eval-model"
  temporary_endpoint_base_name = "${var.deployment_name}-forecast-deepar-eval-endpoint"
  temporary_endpoint_cfg_base  = "${var.deployment_name}-forecast-deepar-eval-endpoint-config"

  # Official SageMaker built-in DeepAR algorithm registry accounts vary by region.
  deepar_repository_account_ids = {
    "eu-west-2" = "644912444149"
    "us-east-1" = "522234722520"
    "us-west-2" = "156387875391"
  }
  deepar_repository_account_id = var.deepar_repository_account_id != null ? var.deepar_repository_account_id : lookup(local.deepar_repository_account_ids, var.aws_region, null)
  deepar_image_uri             = "${local.deepar_repository_account_id}.dkr.ecr.${var.aws_region}.amazonaws.com/forecasting-deepar:${var.deepar_image_tag}"
}

check "deepar_repository_account_id_known" {
  assert {
    condition     = local.deepar_repository_account_id != null
    error_message = "No default SageMaker DeepAR ECR account mapping is configured for this region. Set deepar_repository_account_id explicitly."
  }
}
