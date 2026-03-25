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
  # The local training runner packages and uploads the source bundle at runtime
  # because SageMaker expects a `.tar.gz` source archive rather than a generic
  # zip produced by the Terraform archive provider.
  source_dir             = abspath("${path.module}/../../sagemaker/forecast_training")
  source_bundle_key      = var.source_bundle_key != null ? var.source_bundle_key : "sagemaker/forecast_training/source/forecast_training_source.tar.gz"
  gold_input_s3_uri      = "s3://${var.lakehouse_bucket_name}/${trim(var.gold_forecast_features_prefix, "/")}/"
  training_output_s3_uri = "s3://${var.artefact_bucket_name}/${trim(var.training_output_prefix, "/")}/"
  job_base_name          = var.job_base_name != null ? var.job_base_name : "${var.deployment_name}-forecast-sklearn-train"

  # SageMaker framework container accounts vary by region, so keep a small map
  # for the regions this project actively targets and allow explicit override.
  sklearn_repository_account_ids = {
    "eu-west-2" = "764974769150"
    "us-east-1" = "683313688378"
    "us-west-2" = "246618743249"
  }
  sklearn_repository_account_id = var.sklearn_repository_account_id != null ? var.sklearn_repository_account_id : lookup(local.sklearn_repository_account_ids, var.aws_region, null)
  sklearn_image_tag             = "${var.sklearn_image_version}-cpu-py3"
  sklearn_image_uri             = "${local.sklearn_repository_account_id}.dkr.ecr.${var.aws_region}.amazonaws.com/sagemaker-scikit-learn:${local.sklearn_image_tag}"
}

check "sklearn_repository_account_id_known" {
  assert {
    condition     = local.sklearn_repository_account_id != null
    error_message = "No default SageMaker scikit-learn ECR account mapping is configured for this region. Set sklearn_repository_account_id explicitly."
  }
}
