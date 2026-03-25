output "forecast_endpoint_autoscaling_resource_id" {
  value = aws_appautoscaling_target.forecast_endpoint.resource_id
}

output "forecast_endpoint_autoscaling_policy_name" {
  value = aws_appautoscaling_policy.forecast_target_tracking.name
}

output "forecast_endpoint_model_latency_alarm_name" {
  value = aws_cloudwatch_metric_alarm.high_model_latency.alarm_name
}

output "forecast_endpoint_5xx_alarm_name" {
  value = aws_cloudwatch_metric_alarm.high_5xx_errors.alarm_name
}

output "forecast_endpoint_4xx_alarm_name" {
  value = aws_cloudwatch_metric_alarm.high_4xx_errors.alarm_name
}
