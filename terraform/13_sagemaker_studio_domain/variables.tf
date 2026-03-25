variable "aws_region" {
  description = "AWS region in which the SageMaker Studio resources should be created."
  type        = string
}

variable "deployment_name" {
  description = "Shared deployment identifier produced by the project context module."
  type        = string
}

variable "kms_key_arn" {
  description = "KMS key ARN used by the Studio domain for its encrypted storage."
  type        = string
}

variable "sagemaker_role_arn" {
  description = "IAM role ARN assumed by SageMaker Studio users and spaces."
  type        = string
}

variable "domain_name" {
  description = "Optional explicit name for the SageMaker Studio domain."
  type        = string
  default     = null
}

variable "user_profile_name" {
  description = "Optional explicit name for the initial SageMaker Studio user profile."
  type        = string
  default     = null
}

variable "auth_mode" {
  description = "SageMaker Studio authentication mode. IAM keeps the setup simple for this portfolio stack."
  type        = string
  default     = "IAM"
}

variable "app_network_access_type" {
  description = "Whether Studio apps use public internet access or VPC-only access."
  type        = string
  default     = "PublicInternetOnly"
}

variable "home_efs_retention_mode" {
  description = "Whether the Studio home EFS should be retained or deleted when the domain is destroyed."
  type        = string
  default     = "Delete"
}

variable "vpc_id" {
  description = "Optional VPC ID for the Studio domain. If omitted, the account's default VPC is used."
  type        = string
  default     = null
}

variable "subnet_ids" {
  description = "Optional subnet IDs for the Studio domain. If omitted, subnets from the default VPC are used."
  type        = list(string)
  default     = null
}

variable "tags" {
  description = "Standard tags applied to the SageMaker Studio domain and user profile."
  type        = map(string)
  default     = {}
}
