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
  source_dir             = abspath("${path.module}/../../sagemaker/anomaly_autoencoder_training")
  source_bundle_key      = var.source_bundle_key != null ? var.source_bundle_key : "sagemaker/anomaly_autoencoder_training/source/anomaly_autoencoder_training_source.tar.gz"
  gold_input_s3_uri      = "s3://${var.lakehouse_bucket_name}/${trim(var.gold_anomaly_features_prefix, "/")}/"
  training_output_s3_uri = "s3://${var.artefact_bucket_name}/${trim(var.training_output_prefix, "/")}/"
  job_base_name          = var.job_base_name != null ? var.job_base_name : "${var.deployment_name}-anomaly-autoencoder-train"

  pytorch_repository_account_ids = {
    "eu-west-2" = "763104351884"
    "us-east-1" = "763104351884"
    "us-west-2" = "763104351884"
  }
  pytorch_repository_account_id = var.pytorch_repository_account_id != null ? var.pytorch_repository_account_id : lookup(local.pytorch_repository_account_ids, var.aws_region, null)
  training_image_uri            = "${local.pytorch_repository_account_id}.dkr.ecr.${var.aws_region}.amazonaws.com/pytorch-training:${var.pytorch_training_image_tag}"
  inference_image_uri           = "${local.pytorch_repository_account_id}.dkr.ecr.${var.aws_region}.amazonaws.com/pytorch-inference:${var.pytorch_inference_image_tag}"
}

check "pytorch_repository_account_id_known" {
  assert {
    condition     = local.pytorch_repository_account_id != null
    error_message = "No default SageMaker PyTorch ECR account mapping is configured for this region. Set pytorch_repository_account_id explicitly."
  }
}
