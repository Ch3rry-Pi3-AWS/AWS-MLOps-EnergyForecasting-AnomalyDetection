# Expose the source-bundle destination and derived SageMaker configuration so
# the local training runner can stage code and start jobs without
# reconstructing naming or URIs.
output "forecast_training_source_bundle_s3_uri" {
  value = "s3://${var.artefact_bucket_name}/${local.source_bundle_key}"
}

output "forecast_training_source_bundle_key" {
  value = local.source_bundle_key
}

output "forecast_training_source_dir" {
  value = local.source_dir
}

output "forecast_training_input_s3_uri" {
  value = local.gold_input_s3_uri
}

output "forecast_training_output_s3_uri" {
  value = local.training_output_s3_uri
}

output "forecast_training_job_base_name" {
  value = local.job_base_name
}

output "forecast_training_image_uri" {
  value = local.sklearn_image_uri
}

output "forecast_inference_image_uri" {
  value = local.sklearn_image_uri
}

output "forecast_model_package_group_name" {
  value = var.forecast_model_package_group_name
}

output "forecast_training_role_arn" {
  value = var.sagemaker_role_arn
}

output "forecast_training_region" {
  value = var.aws_region
}

output "forecast_training_kms_key_arn" {
  value = var.kms_key_arn
}
