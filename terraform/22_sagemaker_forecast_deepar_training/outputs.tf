output "forecast_deepar_gold_input_s3_uri" {
  value = local.gold_input_s3_uri
}

output "forecast_deepar_prepared_input_s3_uri" {
  value = local.prepared_input_s3_uri
}

output "forecast_deepar_training_output_s3_uri" {
  value = local.training_output_s3_uri
}

output "forecast_deepar_evaluation_output_s3_uri" {
  value = local.evaluation_output_s3_uri
}

output "forecast_deepar_training_job_base_name" {
  value = local.job_base_name
}

output "forecast_deepar_temporary_model_base_name" {
  value = local.temporary_model_base_name
}

output "forecast_deepar_temporary_endpoint_base_name" {
  value = local.temporary_endpoint_base_name
}

output "forecast_deepar_temporary_endpoint_config_base_name" {
  value = local.temporary_endpoint_cfg_base
}

output "forecast_deepar_training_image_uri" {
  value = local.deepar_image_uri
}

output "forecast_deepar_inference_image_uri" {
  value = local.deepar_image_uri
}

output "forecast_deepar_model_package_group_name" {
  value = var.forecast_model_package_group_name
}

output "forecast_deepar_training_role_arn" {
  value = var.sagemaker_role_arn
}

output "forecast_deepar_training_region" {
  value = var.aws_region
}

output "forecast_deepar_training_kms_key_arn" {
  value = var.kms_key_arn
}

output "forecast_deepar_prediction_length" {
  value = var.prediction_length
}

output "forecast_deepar_context_length" {
  value = var.context_length
}

output "forecast_deepar_time_freq" {
  value = var.time_freq
}

output "forecast_deepar_epochs" {
  value = var.epochs
}

output "forecast_deepar_num_layers" {
  value = var.num_layers
}

output "forecast_deepar_num_cells" {
  value = var.num_cells
}

output "forecast_deepar_mini_batch_size" {
  value = var.mini_batch_size
}

output "forecast_deepar_likelihood" {
  value = var.likelihood
}
