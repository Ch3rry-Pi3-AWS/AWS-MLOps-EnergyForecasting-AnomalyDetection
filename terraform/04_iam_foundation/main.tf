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
  # Keep role names predictable and human-readable while still allowing
  # explicit overrides when a caller needs stricter naming control.
  lambda_role_name    = var.lambda_role_name != null ? var.lambda_role_name : "iam-lambda-${var.deployment_name}"
  glue_role_name      = var.glue_role_name != null ? var.glue_role_name : "iam-glue-${var.deployment_name}"
  sagemaker_role_name = var.sagemaker_role_name != null ? var.sagemaker_role_name : "iam-sagemaker-${var.deployment_name}"

  # S3 IAM permissions are usually split between bucket-level actions such
  # as list/get location and object-level actions such as put/get/delete.
  bucket_arns = [var.lakehouse_bucket_arn, var.artefact_bucket_arn, var.monitoring_bucket_arn]
  object_arns = [for arn in local.bucket_arns : "${arn}/*"]
}

# Trust policy: allow the Lambda service to assume the ingestion role.
data "aws_iam_policy_document" "lambda_assume_role" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

# Trust policy: allow AWS Glue jobs to assume the Glue service role.
data "aws_iam_policy_document" "glue_assume_role" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["glue.amazonaws.com"]
    }
  }
}

# Trust policy: allow SageMaker jobs, pipelines, and endpoints to assume the
# execution role created by this module.
data "aws_iam_policy_document" "sagemaker_assume_role" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["sagemaker.amazonaws.com"]
    }
  }
}

# Grant the Lambda role enough access to read and write objects and to use
# the shared KMS key when data is encrypted.
data "aws_iam_policy_document" "lambda_data_access" {
  statement {
    sid       = "BucketList"
    actions   = ["s3:GetBucketLocation", "s3:ListBucket"]
    resources = local.bucket_arns
  }

  statement {
    sid = "ObjectReadWrite"
    actions = [
      "s3:DeleteObject",
      "s3:GetObject",
      "s3:PutObject",
    ]
    resources = local.object_arns
  }

  statement {
    sid = "KmsUsage"
    actions = [
      "kms:Decrypt",
      "kms:DescribeKey",
      "kms:Encrypt",
      "kms:GenerateDataKey",
    ]
    resources = [var.kms_key_arn]
  }
}

# Glue needs similar data access plus the ability to emit logs and metrics
# while transformation jobs are running.
data "aws_iam_policy_document" "glue_data_access" {
  statement {
    sid       = "BucketList"
    actions   = ["s3:GetBucketLocation", "s3:ListBucket"]
    resources = local.bucket_arns
  }

  statement {
    sid = "ObjectReadWrite"
    actions = [
      "s3:DeleteObject",
      "s3:GetObject",
      "s3:PutObject",
    ]
    resources = local.object_arns
  }

  statement {
    sid = "KmsUsage"
    actions = [
      "kms:Decrypt",
      "kms:DescribeKey",
      "kms:Encrypt",
      "kms:GenerateDataKey",
    ]
    resources = [var.kms_key_arn]
  }

  statement {
    sid = "LogsAndMetrics"
    actions = [
      "cloudwatch:PutMetricData",
      "logs:CreateLogGroup",
      "logs:CreateLogStream",
      "logs:DescribeLogGroups",
      "logs:DescribeLogStreams",
      "logs:GetLogEvents",
      "logs:PutLogEvents",
    ]
    resources = ["*"]
  }
}

# SageMaker needs data access, KMS usage, observability permissions, and ECR
# image-pull permissions for container-based training or inference workloads.
data "aws_iam_policy_document" "sagemaker_execution" {
  statement {
    sid       = "BucketList"
    actions   = ["s3:GetBucketLocation", "s3:ListBucket"]
    resources = local.bucket_arns
  }

  statement {
    sid = "ObjectReadWrite"
    actions = [
      "s3:DeleteObject",
      "s3:GetObject",
      "s3:PutObject",
    ]
    resources = local.object_arns
  }

  statement {
    sid = "KmsUsage"
    actions = [
      "kms:Decrypt",
      "kms:DescribeKey",
      "kms:Encrypt",
      "kms:GenerateDataKey",
    ]
    resources = [var.kms_key_arn]
  }

  statement {
    sid = "LogsAndMetrics"
    actions = [
      "cloudwatch:PutMetricData",
      "logs:CreateLogGroup",
      "logs:CreateLogStream",
      "logs:PutLogEvents",
    ]
    resources = ["*"]
  }

  statement {
    sid = "EcrRead"
    actions = [
      "ecr:BatchGetImage",
      "ecr:DescribeImages",
      "ecr:GetAuthorizationToken",
      "ecr:GetDownloadUrlForLayer",
    ]
    resources = ["*"]
  }

  # Studio uses the SageMaker execution role to read back domain and registry
  # metadata in the UI. Without these describe/list calls, the domain can
  # exist but the user still sees "permissions not configured correctly".
  statement {
    sid = "StudioMetadataRead"
    actions = [
      "sagemaker:CreatePresignedDomainUrl",
      "sagemaker:DescribeApp",
      "sagemaker:DescribeDomain",
      "sagemaker:DescribeImage",
      "sagemaker:DescribeImageVersion",
      "sagemaker:DescribeModelPackage",
      "sagemaker:DescribeModelPackageGroup",
      "sagemaker:DescribeSpace",
      "sagemaker:DescribeStudioLifecycleConfig",
      "sagemaker:DescribeUserProfile",
      "sagemaker:ListApps",
      "sagemaker:ListDomains",
      "sagemaker:ListImageVersions",
      "sagemaker:ListImages",
      "sagemaker:ListModelPackages",
      "sagemaker:ListModelPackageGroups",
      "sagemaker:ListSpaces",
      "sagemaker:ListStudioLifecycleConfigs",
      "sagemaker:ListUserProfiles",
      "sagemaker:Search",
    ]
    resources = ["*"]
  }
}

# Create the execution roles that later service-specific modules will reuse.
resource "aws_iam_role" "lambda_ingestion" {
  name               = local.lambda_role_name
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json
  tags               = merge(var.tags, { Name = local.lambda_role_name })
}

resource "aws_iam_role" "glue_service" {
  name               = local.glue_role_name
  assume_role_policy = data.aws_iam_policy_document.glue_assume_role.json
  tags               = merge(var.tags, { Name = local.glue_role_name })
}

resource "aws_iam_role" "sagemaker_execution" {
  name               = local.sagemaker_role_name
  assume_role_policy = data.aws_iam_policy_document.sagemaker_assume_role.json
  tags               = merge(var.tags, { Name = local.sagemaker_role_name })
}

# Materialise the custom permission policies separately so they can be
# attached cleanly and inspected independently in IAM.
resource "aws_iam_policy" "lambda_data_access" {
  name   = "${local.lambda_role_name}-policy"
  policy = data.aws_iam_policy_document.lambda_data_access.json
}

resource "aws_iam_policy" "glue_data_access" {
  name   = "${local.glue_role_name}-policy"
  policy = data.aws_iam_policy_document.glue_data_access.json
}

resource "aws_iam_policy" "sagemaker_execution" {
  name   = "${local.sagemaker_role_name}-policy"
  policy = data.aws_iam_policy_document.sagemaker_execution.json
}

# Attach the standard AWS-managed basic execution policy for Lambda logs.
resource "aws_iam_role_policy_attachment" "lambda_basic_execution" {
  role       = aws_iam_role.lambda_ingestion.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# Attach the custom data/KMS access policies alongside the managed service
# policies needed by Glue and Lambda.
resource "aws_iam_role_policy_attachment" "lambda_data_access" {
  role       = aws_iam_role.lambda_ingestion.name
  policy_arn = aws_iam_policy.lambda_data_access.arn
}

resource "aws_iam_role_policy_attachment" "glue_service_role" {
  role       = aws_iam_role.glue_service.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSGlueServiceRole"
}

resource "aws_iam_role_policy_attachment" "glue_data_access" {
  role       = aws_iam_role.glue_service.name
  policy_arn = aws_iam_policy.glue_data_access.arn
}

resource "aws_iam_role_policy_attachment" "sagemaker_execution" {
  role       = aws_iam_role.sagemaker_execution.name
  policy_arn = aws_iam_policy.sagemaker_execution.arn
}
