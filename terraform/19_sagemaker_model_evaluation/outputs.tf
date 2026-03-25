# Expose evaluation-report locations and threshold settings so the local
# evaluation runner can stay declarative and avoid hardcoded promotion rules.
output "evaluation_region" {
  value = var.aws_region
}

output "evaluation_kms_key_arn" {
  value = var.kms_key_arn
}

output "evaluation_artifact_bucket_name" {
  value = var.artefact_bucket_name
}

output "forecast_model_package_group_name" {
  value = var.forecast_model_package_group_name
}

output "anomaly_model_package_group_name" {
  value = var.anomaly_model_package_group_name
}

output "forecast_evaluation_report_prefix" {
  value = local.forecast_report_prefix
}

output "anomaly_evaluation_report_prefix" {
  value = local.anomaly_report_prefix
}

output "forecast_evaluation_report_s3_uri" {
  value = local.forecast_report_s3_uri
}

output "anomaly_evaluation_report_s3_uri" {
  value = local.anomaly_report_s3_uri
}

output "forecast_min_training_rows" {
  value = var.forecast_min_training_rows
}

output "forecast_max_mae" {
  value = var.forecast_max_mae
}

output "forecast_max_rmse" {
  value = var.forecast_max_rmse
}

output "forecast_min_r2" {
  value = var.forecast_min_r2
}

output "anomaly_min_training_rows" {
  value = var.anomaly_min_training_rows
}

output "anomaly_min_anomaly_rate" {
  value = var.anomaly_min_anomaly_rate
}

output "anomaly_max_anomaly_rate" {
  value = var.anomaly_max_anomaly_rate
}
