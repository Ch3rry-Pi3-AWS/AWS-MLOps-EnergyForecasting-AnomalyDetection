# Surface the model package group names and ARNs so later training and
# deployment modules can register model versions without reconstructing names.
output "forecast_model_package_group_name" {
  value = aws_sagemaker_model_package_group.forecast.model_package_group_name
}

output "forecast_model_package_group_arn" {
  value = aws_sagemaker_model_package_group.forecast.arn
}

output "anomaly_model_package_group_name" {
  value = aws_sagemaker_model_package_group.anomaly.model_package_group_name
}

output "anomaly_model_package_group_arn" {
  value = aws_sagemaker_model_package_group.anomaly.arn
}
