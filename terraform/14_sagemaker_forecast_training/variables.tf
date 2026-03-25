variable "aws_region" {
  description = "AWS region in which forecast training assets should be staged."
  type        = string
}

variable "deployment_name" {
  description = "Shared deployment identifier produced by the project context module."
  type        = string
}

variable "kms_key_arn" {
  description = "KMS key ARN used to encrypt the uploaded training source bundle."
  type        = string
}

variable "artefact_bucket_name" {
  description = "Name of the S3 artefact bucket used to store training source bundles and model outputs."
  type        = string
}

variable "lakehouse_bucket_name" {
  description = "Name of the S3 lakehouse bucket that stores Gold forecast features."
  type        = string
}

variable "sagemaker_role_arn" {
  description = "IAM role ARN assumed by the SageMaker training job."
  type        = string
}

variable "forecast_model_package_group_name" {
  description = "Name of the forecast model package group that trained model versions should be registered into."
  type        = string
}

variable "job_base_name" {
  description = "Optional deterministic base name used by the forecast training runner before it appends a timestamp."
  type        = string
  default     = null
}

variable "source_bundle_key" {
  description = "Optional object key used when uploading the forecast training source bundle to the artefact bucket."
  type        = string
  default     = null
}

variable "gold_forecast_features_prefix" {
  description = "Lakehouse prefix under which the Gold forecast-features dataset is stored."
  type        = string
  default     = "gold/forecast_features"
}

variable "training_output_prefix" {
  description = "Artefact-bucket prefix under which SageMaker training outputs should be written."
  type        = string
  default     = "sagemaker/forecast_training/output"
}

variable "sklearn_image_version" {
  description = "SageMaker scikit-learn framework image version used for training and inference registration."
  type        = string
  default     = "1.2-1"
}

variable "sklearn_repository_account_id" {
  description = "Optional explicit ECR account ID for the SageMaker scikit-learn framework image in this region."
  type        = string
  default     = null
}
