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
  # Keep the schedule and role names aligned with the shared deployment name
  # unless the caller explicitly overrides them.
  schedule_name = var.schedule_name != null ? var.schedule_name : "scheduler-ingestion-${var.deployment_name}"
  role_name     = var.scheduler_role_name != null ? var.scheduler_role_name : "iam-scheduler-${var.deployment_name}"
}

# Trust policy: allow EventBridge Scheduler to assume the execution role that
# will invoke the Lambda ingestion function.
data "aws_iam_policy_document" "scheduler_assume_role" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["scheduler.amazonaws.com"]
    }
  }
}

# Grant the scheduler permission to invoke only the target Lambda function.
data "aws_iam_policy_document" "scheduler_invoke_lambda" {
  statement {
    sid       = "InvokeLambdaIngestion"
    actions   = ["lambda:InvokeFunction"]
    resources = [var.lambda_function_arn]
  }
}

resource "aws_iam_role" "scheduler" {
  name               = local.role_name
  assume_role_policy = data.aws_iam_policy_document.scheduler_assume_role.json

  tags = merge(
    var.tags,
    {
      Name      = local.role_name
      Component = "eventbridge-scheduler"
    }
  )
}

resource "aws_iam_policy" "scheduler_invoke_lambda" {
  name   = "${local.role_name}-policy"
  policy = data.aws_iam_policy_document.scheduler_invoke_lambda.json
}

resource "aws_iam_role_policy_attachment" "scheduler_invoke_lambda" {
  role       = aws_iam_role.scheduler.name
  policy_arn = aws_iam_policy.scheduler_invoke_lambda.arn
}

# Create the recurring schedule that drives near-real-time ingestion.
resource "aws_scheduler_schedule" "main" {
  name                         = local.schedule_name
  description                  = var.description
  group_name                   = var.group_name
  schedule_expression          = var.schedule_expression
  schedule_expression_timezone = var.schedule_expression_timezone
  state                        = var.schedule_state

  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = var.lambda_function_arn
    role_arn = aws_iam_role.scheduler.arn
    input    = jsonencode(var.scheduler_payload)
  }

  depends_on = [aws_iam_role_policy_attachment.scheduler_invoke_lambda]
}

# Add an explicit Lambda permission so Scheduler is allowed to invoke the
# function from this specific schedule ARN.
resource "aws_lambda_permission" "allow_scheduler" {
  statement_id  = "AllowExecutionFromEventBridgeScheduler"
  action        = "lambda:InvokeFunction"
  function_name = var.lambda_function_name
  principal     = "scheduler.amazonaws.com"
  source_arn    = aws_scheduler_schedule.main.arn
}

