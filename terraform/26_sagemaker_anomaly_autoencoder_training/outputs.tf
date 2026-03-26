output "anomaly_autoencoder_training_source_bundle_s3_uri" {
  value = "s3://${var.artefact_bucket_name}/${local.source_bundle_key}"
}

output "anomaly_autoencoder_training_source_bundle_key" {
  value = local.source_bundle_key
}

output "anomaly_autoencoder_training_source_dir" {
  value = local.source_dir
}

output "anomaly_autoencoder_training_input_s3_uri" {
  value = local.gold_input_s3_uri
}

output "anomaly_autoencoder_training_output_s3_uri" {
  value = local.training_output_s3_uri
}

output "anomaly_autoencoder_training_job_base_name" {
  value = local.job_base_name
}

output "anomaly_autoencoder_training_image_uri" {
  value = local.training_image_uri
}

output "anomaly_autoencoder_inference_image_uri" {
  value = local.inference_image_uri
}

output "anomaly_autoencoder_model_package_group_name" {
  value = var.anomaly_model_package_group_name
}

output "anomaly_autoencoder_training_role_arn" {
  value = var.sagemaker_role_arn
}

output "anomaly_autoencoder_training_region" {
  value = var.aws_region
}

output "anomaly_autoencoder_training_kms_key_arn" {
  value = var.kms_key_arn
}

output "anomaly_autoencoder_hidden_dim" {
  value = var.hidden_dim
}

output "anomaly_autoencoder_latent_dim" {
  value = var.latent_dim
}

output "anomaly_autoencoder_max_epochs" {
  value = var.max_epochs
}

output "anomaly_autoencoder_batch_size" {
  value = var.batch_size
}

output "anomaly_autoencoder_learning_rate" {
  value = var.learning_rate
}

output "anomaly_autoencoder_score_quantile" {
  value = var.score_quantile
}
