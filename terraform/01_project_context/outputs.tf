# Expose the generated context so scripts and downstream modules can
# consume it without re-deriving values independently.
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

# Emit tags as JSON because the Python deploy script reads outputs via
# `terraform output -raw`, which is easiest to consume as a string.
output "standard_tags_json" {
  value = jsonencode(local.standard_tags)
}
