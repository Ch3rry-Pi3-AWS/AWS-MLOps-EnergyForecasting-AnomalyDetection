# Expose the durable endpoint naming and deployment configuration so the local
# runner can resolve the latest approved model package and create or update the
# actual endpoint resources without reconstructing names.
output "anomaly_endpoint_name" {
  value = local.endpoint_name
}

output "anomaly_endpoint_model_name_base" {
  value = local.model_name_base
}

output "anomaly_endpoint_config_name_base" {
  value = local.endpoint_config_name_base
}

output "anomaly_endpoint_instance_type" {
  value = var.instance_type
}

output "anomaly_endpoint_initial_instance_count" {
  value = var.initial_instance_count
}

output "anomaly_endpoint_variant_name" {
  value = var.variant_name
}

output "anomaly_endpoint_region" {
  value = var.aws_region
}

output "anomaly_endpoint_kms_key_arn" {
  value = var.kms_key_arn
}

output "anomaly_endpoint_role_arn" {
  value = var.sagemaker_role_arn
}

output "anomaly_model_package_group_name" {
  value = var.anomaly_model_package_group_name
}
