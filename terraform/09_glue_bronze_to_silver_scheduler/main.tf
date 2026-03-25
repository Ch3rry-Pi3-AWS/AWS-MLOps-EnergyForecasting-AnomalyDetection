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
  # Keep the schedule and target role names aligned with the shared
  # deployment identity unless the caller explicitly overrides them.
  schedule_name = var.schedule_name != null ? var.schedule_name : "scheduler-bronze-silver-${var.deployment_name}"
  role_name     = var.scheduler_role_name != null ? var.scheduler_role_name : "iam-scheduler-glue-${var.deployment_name}"

  # EventBridge Scheduler universal targets invoke an AWS API operation
  # directly. Here the schedule calls Glue StartJobRun with the deployed job
  # name and any optional per-run arguments supplied by the caller.
  start_job_run_input = merge(
    {
      JobName              = var.glue_job_name
      JobRunQueuingEnabled = var.job_run_queuing_enabled
    },
    length(var.job_run_arguments) > 0 ? { Arguments = var.job_run_arguments } : {}
  )
}

# Trust policy: allow EventBridge Scheduler to assume the role used to call
# Glue StartJobRun on the Bronze-to-Silver job.
data "aws_iam_policy_document" "scheduler_assume_role" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["scheduler.amazonaws.com"]
    }
  }
}

# Keep the scheduler permission narrow by granting access only to the deployed
# Bronze-to-Silver Glue job rather than to Glue jobs in general.
data "aws_iam_policy_document" "scheduler_start_glue_job" {
  statement {
    sid       = "StartBronzeToSilverJob"
    actions   = ["glue:StartJobRun"]
    resources = [var.glue_job_arn]
  }
}

resource "aws_iam_role" "scheduler" {
  name               = local.role_name
  assume_role_policy = data.aws_iam_policy_document.scheduler_assume_role.json

  tags = merge(
    var.tags,
    {
      Name      = local.role_name
      Component = "eventbridge-glue-scheduler"
      DataLayer = "silver"
    }
  )
}

resource "aws_iam_policy" "scheduler_start_glue_job" {
  name   = "${local.role_name}-policy"
  policy = data.aws_iam_policy_document.scheduler_start_glue_job.json
}

resource "aws_iam_role_policy_attachment" "scheduler_start_glue_job" {
  role       = aws_iam_role.scheduler.name
  policy_arn = aws_iam_policy.scheduler_start_glue_job.arn
}

# Use a universal target so Scheduler can call the Glue StartJobRun API
# directly without introducing an extra Lambda wrapper.
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
    arn      = "arn:aws:scheduler:::aws-sdk:glue:startJobRun"
    role_arn = aws_iam_role.scheduler.arn
    input    = jsonencode(local.start_job_run_input)

    retry_policy {
      maximum_event_age_in_seconds = var.maximum_event_age_in_seconds
      maximum_retry_attempts       = var.maximum_retry_attempts
    }
  }

  depends_on = [aws_iam_role_policy_attachment.scheduler_start_glue_job]
}
