terraform {
  required_version = ">= 1.5"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.5"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

locals {
  function_name       = var.lambda_function_name != null ? var.lambda_function_name : "lambda-ingest-${var.deployment_name}"
  source_dir          = "${path.module}/../../lambda/ingestion"
  package_output_path = "${path.module}/lambda_ingestion.zip"
}

data "archive_file" "lambda_package" {
  type        = "zip"
  source_dir  = local.source_dir
  output_path = local.package_output_path
}

resource "aws_cloudwatch_log_group" "main" {
  name              = "/aws/lambda/${local.function_name}"
  retention_in_days = var.log_retention_in_days

  tags = merge(
    var.tags,
    {
      Name      = local.function_name
      Component = "lambda-ingestion"
    }
  )
}

resource "aws_lambda_function" "main" {
  function_name = local.function_name
  role          = var.lambda_role_arn
  runtime       = var.runtime
  handler       = var.handler
  filename      = data.archive_file.lambda_package.output_path

  source_code_hash = data.archive_file.lambda_package.output_base64sha256
  memory_size      = var.memory_size
  timeout          = var.timeout_seconds
  kms_key_arn      = var.kms_key_arn
  architectures    = [var.architecture]

  environment {
    variables = {
      PROJECT_ENV          = var.environment
      DEPLOYMENT_NAME      = var.deployment_name
      LAKEHOUSE_BUCKET     = var.lakehouse_bucket_name
      BRONZE_INGEST_PREFIX = var.bronze_ingestion_prefix
      KMS_KEY_ARN          = var.kms_key_arn
      ENERGY_API_BASE_URL  = var.energy_api_base_url
      WEATHER_API_BASE_URL = var.weather_api_base_url
    }
  }

  tags = merge(
    var.tags,
    {
      Name      = local.function_name
      Component = "lambda-ingestion"
    }
  )

  depends_on = [aws_cloudwatch_log_group.main]
}
