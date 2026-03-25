# Expose the durable endpoint naming and deployment configuration so the local
# runner can resolve the latest approved model package and create or update the
# actual endpoint resources without reconstructing names.
output "forecast_endpoint_name" {
  value = local.endpoint_name
}

output "forecast_endpoint_model_name_base" {
  value = local.model_name_base
}

output "forecast_endpoint_config_name_base" {
  value = local.endpoint_config_name_base
}

output "forecast_endpoint_instance_type" {
  value = var.instance_type
}

output "forecast_endpoint_initial_instance_count" {
  value = var.initial_instance_count
}

output "forecast_endpoint_variant_name" {
  value = var.variant_name
}

output "forecast_endpoint_region" {
  value = var.aws_region
}

output "forecast_endpoint_kms_key_arn" {
  value = var.kms_key_arn
}

output "forecast_endpoint_role_arn" {
  value = var.sagemaker_role_arn
}

output "forecast_model_package_group_name" {
  value = var.forecast_model_package_group_name
}
