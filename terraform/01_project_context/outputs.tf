output "aws_region" {
  value = var.aws_region
}

output "environment" {
  value = var.environment
}

output "project_name" {
  value = var.project_name
}

output "project_slug" {
  value = var.project_slug
}

output "resource_prefix" {
  value = var.resource_prefix
}

output "stack_suffix" {
  value = random_pet.stack.id
}

output "deployment_name" {
  value = local.deployment_name
}

output "standard_tags_json" {
  value = jsonencode(local.standard_tags)
}

