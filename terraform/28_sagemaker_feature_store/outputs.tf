output "feature_store_region" {
  value = var.aws_region
}

output "feature_store_record_identifier_feature_name" {
  value = var.record_identifier_feature_name
}

output "feature_store_event_time_feature_name" {
  value = var.event_time_feature_name
}

output "forecast_feature_group_name" {
  value = aws_sagemaker_feature_group.forecast.feature_group_name
}

output "forecast_feature_group_arn" {
  value = aws_sagemaker_feature_group.forecast.arn
}

output "forecast_feature_store_offline_s3_uri" {
  value = local.forecast_offline_store_s3_uri
}

output "forecast_feature_store_gold_input_s3_uri" {
  value = local.forecast_gold_input_s3_uri
}

output "anomaly_feature_group_name" {
  value = aws_sagemaker_feature_group.anomaly.feature_group_name
}

output "anomaly_feature_group_arn" {
  value = aws_sagemaker_feature_group.anomaly.arn
}

output "anomaly_feature_store_offline_s3_uri" {
  value = local.anomaly_offline_store_s3_uri
}

output "anomaly_feature_store_gold_input_s3_uri" {
  value = local.anomaly_gold_input_s3_uri
}
