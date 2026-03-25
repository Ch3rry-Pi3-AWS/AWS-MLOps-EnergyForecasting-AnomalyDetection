variable "aws_region" {
  description = "AWS region in which the anomaly endpoint should be deployed."
  type        = string
}

variable "deployment_name" {
  description = "Shared deployment identifier produced by the project context module."
  type        = string
}

variable "kms_key_arn" {
  description = "KMS key ARN used for endpoint configuration encryption where applicable."
  type        = string
}

variable "sagemaker_role_arn" {
  description = "IAM role ARN assumed by the SageMaker hosted model."
  type        = string
}

variable "anomaly_model_package_group_name" {
  description = "Name of the anomaly model package group whose approved packages are eligible for deployment."
  type        = string
}

variable "endpoint_name" {
  description = "Optional stable SageMaker endpoint name."
  type        = string
  default     = null
}

variable "model_name_base" {
  description = "Optional base name used for the concrete SageMaker model resource created during endpoint deployment."
  type        = string
  default     = null
}

variable "endpoint_config_name_base" {
  description = "Optional base name used for the concrete SageMaker endpoint configuration created during deployment."
  type        = string
  default     = null
}

variable "instance_type" {
  description = "SageMaker instance type used by the hosted endpoint."
  type        = string
  default     = "ml.m5.large"
}

variable "initial_instance_count" {
  description = "Initial number of instances used by the hosted anomaly endpoint."
  type        = number
  default     = 1
}

variable "variant_name" {
  description = "Production variant name used by the hosted endpoint."
  type        = string
  default     = "AllTraffic"
}
