# Surface role names and ARNs so later Terraform modules can reuse the
# execution roles without duplicating IAM creation logic.
output "lambda_role_name" {
  value = aws_iam_role.lambda_ingestion.name
}

output "lambda_role_arn" {
  value = aws_iam_role.lambda_ingestion.arn
}

output "glue_role_name" {
  value = aws_iam_role.glue_service.name
}

output "glue_role_arn" {
  value = aws_iam_role.glue_service.arn
}

output "sagemaker_role_name" {
  value = aws_iam_role.sagemaker_execution.name
}

output "sagemaker_role_arn" {
  value = aws_iam_role.sagemaker_execution.arn
}
