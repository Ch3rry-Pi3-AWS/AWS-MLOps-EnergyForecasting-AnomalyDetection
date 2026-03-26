output "forecast_tft_training_source_bundle_s3_uri" {
  value = "s3://${var.artefact_bucket_name}/${local.source_bundle_key}"
}

output "forecast_tft_training_source_bundle_key" {
  value = local.source_bundle_key
}

output "forecast_tft_training_source_dir" {
  value = local.source_dir
}

output "forecast_tft_training_input_s3_uri" {
  value = local.gold_input_s3_uri
}

output "forecast_tft_training_output_s3_uri" {
  value = local.training_output_s3_uri
}

output "forecast_tft_training_job_base_name" {
  value = local.job_base_name
}

output "forecast_tft_training_image_uri" {
  value = local.training_image_uri
}

output "forecast_tft_inference_image_uri" {
  value = local.inference_image_uri
}

output "forecast_tft_model_package_group_name" {
  value = var.forecast_model_package_group_name
}

output "forecast_tft_training_role_arn" {
  value = var.sagemaker_role_arn
}

output "forecast_tft_training_region" {
  value = var.aws_region
}

output "forecast_tft_training_kms_key_arn" {
  value = var.kms_key_arn
}

output "forecast_tft_context_length" {
  value = var.context_length
}

output "forecast_tft_prediction_length" {
  value = var.prediction_length
}

output "forecast_tft_max_epochs" {
  value = var.max_epochs
}

output "forecast_tft_batch_size" {
  value = var.batch_size
}

output "forecast_tft_hidden_size" {
  value = var.hidden_size
}

output "forecast_tft_attention_head_size" {
  value = var.attention_head_size
}

output "forecast_tft_hidden_continuous_size" {
  value = var.hidden_continuous_size
}

output "forecast_tft_dropout" {
  value = var.dropout
}

output "forecast_tft_learning_rate" {
  value = var.learning_rate
}
