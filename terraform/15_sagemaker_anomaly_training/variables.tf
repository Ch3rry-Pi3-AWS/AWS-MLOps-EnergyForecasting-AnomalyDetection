variable "aws_region" {
  description = "AWS region in which anomaly training assets should be staged."
  type        = string
}

variable "deployment_name" {
  description = "Shared deployment identifier produced by the project context module."
  type        = string
}

variable "kms_key_arn" {
  description = "KMS key ARN used to encrypt the uploaded anomaly-training source bundle."
  type        = string
}

variable "artefact_bucket_name" {
  description = "Name of the S3 artefact bucket used to store anomaly-training source bundles and model outputs."
  type        = string
}

variable "lakehouse_bucket_name" {
  description = "Name of the S3 lakehouse bucket that stores Gold anomaly features."
  type        = string
}

variable "sagemaker_role_arn" {
  description = "IAM role ARN assumed by the SageMaker anomaly-training job."
  type        = string
}

variable "anomaly_model_package_group_name" {
  description = "Name of the anomaly model package group that trained anomaly model versions should be registered into."
  type        = string
}

variable "job_base_name" {
  description = "Optional deterministic base name used by the anomaly-training runner before it appends a timestamp."
  type        = string
  default     = null
}

variable "source_bundle_key" {
  description = "Optional object key used when uploading the anomaly-training source bundle to the artefact bucket."
  type        = string
  default     = null
}

variable "gold_anomaly_features_prefix" {
  description = "Lakehouse prefix under which the Gold anomaly-features dataset is stored."
  type        = string
  default     = "gold/anomaly_features"
}

variable "training_output_prefix" {
  description = "Artefact-bucket prefix under which SageMaker anomaly-training outputs should be written."
  type        = string
  default     = "sagemaker/anomaly_training/output"
}

variable "sklearn_image_version" {
  description = "SageMaker scikit-learn framework image version used for anomaly training and inference registration."
  type        = string
  default     = "1.2-1"
}

variable "sklearn_repository_account_id" {
  description = "Optional explicit ECR account ID for the SageMaker scikit-learn framework image in this region."
  type        = string
  default     = null
}
