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
  # Keep the function name aligned with the shared deployment identity while
  # still allowing an override if a caller wants something explicit.
  function_name = var.lambda_function_name != null ? var.lambda_function_name : "lambda-ingest-${var.deployment_name}"

  # Package the starter Lambda directly from the repository so the module can
  # be applied without a separate build system at this stage of the project.
  source_dir          = "${path.module}/../../lambda/ingestion"
  package_output_path = "${path.module}/lambda_ingestion.zip"
}

# Zip the local Lambda source into a deployment package Terraform can pass to
# the Lambda service.
data "archive_file" "lambda_package" {
  type        = "zip"
  source_dir  = local.source_dir
  output_path = local.package_output_path
}

# Create the log group explicitly so retention is managed by Terraform rather
# than accepting Lambda's indefinitely retained default behaviour.
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

# Deploy the starter ingestion Lambda. For now it writes Bronze ingestion
# manifests so the platform can prove packaging, IAM, S3, and KMS wiring
# before richer API-fetch logic is introduced.
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

  # Pass only application-specific variables here. Reserved runtime
  # variables such as AWS_REGION are provided by Lambda automatically.
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

  # Ensure the log group exists before the function is created so retention
  # policy is under Terraform control from the first invocation.
  depends_on = [aws_cloudwatch_log_group.main]
}
