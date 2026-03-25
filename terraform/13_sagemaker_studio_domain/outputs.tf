# Surface the domain and first user profile so later SageMaker stages can
# target the Studio environment directly when needed.
output "sagemaker_domain_id" {
  value = aws_sagemaker_domain.main.id
}

output "sagemaker_domain_arn" {
  value = aws_sagemaker_domain.main.arn
}

output "sagemaker_domain_name" {
  value = aws_sagemaker_domain.main.domain_name
}

output "sagemaker_domain_url" {
  value = aws_sagemaker_domain.main.url
}

output "sagemaker_user_profile_name" {
  value = aws_sagemaker_user_profile.default.user_profile_name
}

output "sagemaker_user_profile_arn" {
  value = aws_sagemaker_user_profile.default.arn
}
