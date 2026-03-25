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
  resource_id = "endpoint/${var.forecast_endpoint_name}/variant/${var.forecast_endpoint_variant_name}"

  alarm_dimensions = {
    EndpointName = var.forecast_endpoint_name
    VariantName  = var.forecast_endpoint_variant_name
  }

  high_model_latency_alarm_name = "${var.deployment_name}-forecast-endpoint-model-latency"
  high_5xx_alarm_name           = "${var.deployment_name}-forecast-endpoint-5xx-errors"
  high_4xx_alarm_name           = "${var.deployment_name}-forecast-endpoint-4xx-errors"
}

# This stage assumes the stable forecast endpoint already exists. Terraform
# manages autoscaling and alarming around that endpoint, but it does not create
# the endpoint itself.
resource "aws_appautoscaling_target" "forecast_endpoint" {
  max_capacity       = var.max_instance_count
  min_capacity       = var.min_instance_count
  resource_id        = local.resource_id
  scalable_dimension = "sagemaker:variant:DesiredInstanceCount"
  service_namespace  = "sagemaker"
}

resource "aws_appautoscaling_policy" "forecast_target_tracking" {
  name               = "${var.deployment_name}-forecast-invocations-scaling"
  policy_type        = "TargetTrackingScaling"
  resource_id        = aws_appautoscaling_target.forecast_endpoint.resource_id
  scalable_dimension = aws_appautoscaling_target.forecast_endpoint.scalable_dimension
  service_namespace  = aws_appautoscaling_target.forecast_endpoint.service_namespace

  target_tracking_scaling_policy_configuration {
    predefined_metric_specification {
      predefined_metric_type = "SageMakerVariantInvocationsPerInstance"
    }

    target_value       = var.target_invocations_per_instance
    scale_in_cooldown  = var.scale_in_cooldown_seconds
    scale_out_cooldown = var.scale_out_cooldown_seconds
  }
}

resource "aws_cloudwatch_metric_alarm" "high_model_latency" {
  alarm_name          = local.high_model_latency_alarm_name
  alarm_description   = "High average forecast-endpoint model latency."
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = var.latency_evaluation_periods
  metric_name         = "ModelLatency"
  namespace           = "AWS/SageMaker"
  period              = var.latency_period_seconds
  statistic           = "Average"
  threshold           = var.model_latency_threshold_microseconds
  treat_missing_data  = "notBreaching"
  alarm_actions       = var.alarm_actions
  ok_actions          = var.ok_actions
  dimensions          = local.alarm_dimensions
}

resource "aws_cloudwatch_metric_alarm" "high_5xx_errors" {
  alarm_name          = local.high_5xx_alarm_name
  alarm_description   = "Forecast endpoint returned 5XX invocation errors."
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = var.error_evaluation_periods
  metric_name         = "Invocation5XXErrors"
  namespace           = "AWS/SageMaker"
  period              = var.error_period_seconds
  statistic           = "Sum"
  threshold           = var.invocation_5xx_threshold
  treat_missing_data  = "notBreaching"
  alarm_actions       = var.alarm_actions
  ok_actions          = var.ok_actions
  dimensions          = local.alarm_dimensions
}

resource "aws_cloudwatch_metric_alarm" "high_4xx_errors" {
  alarm_name          = local.high_4xx_alarm_name
  alarm_description   = "Forecast endpoint returned 4XX invocation errors."
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = var.error_evaluation_periods
  metric_name         = "Invocation4XXErrors"
  namespace           = "AWS/SageMaker"
  period              = var.error_period_seconds
  statistic           = "Sum"
  threshold           = var.invocation_4xx_threshold
  treat_missing_data  = "notBreaching"
  alarm_actions       = var.alarm_actions
  ok_actions          = var.ok_actions
  dimensions          = local.alarm_dimensions
}
