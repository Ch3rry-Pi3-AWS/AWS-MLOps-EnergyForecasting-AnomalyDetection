variable "aws_region" {
  description = "AWS region in which the SageMaker Feature Store resources should be created."
  type        = string
}

variable "deployment_name" {
  description = "Shared deployment identifier produced by the project context module."
  type        = string
}

variable "kms_key_arn" {
  description = "KMS key ARN used to encrypt the offline Feature Store S3 prefixes."
  type        = string
}

variable "lakehouse_bucket_name" {
  description = "Name of the S3 lakehouse bucket that stores Gold features and Feature Store offline data."
  type        = string
}

variable "sagemaker_role_arn" {
  description = "IAM role ARN used by SageMaker Feature Store for offline-store access."
  type        = string
}

variable "feature_store_prefix" {
  description = "Root lakehouse prefix under which the Feature Store offline data should be written."
  type        = string
  default     = "feature_store"
}

variable "gold_forecast_features_prefix" {
  description = "Lakehouse prefix under which the Gold forecast-features dataset is stored."
  type        = string
  default     = "gold/forecast_features"
}

variable "gold_anomaly_features_prefix" {
  description = "Lakehouse prefix under which the Gold anomaly-features dataset is stored."
  type        = string
  default     = "gold/anomaly_features"
}

variable "forecast_feature_group_name" {
  description = "Optional explicit name for the forecast Feature Group."
  type        = string
  default     = null
}

variable "anomaly_feature_group_name" {
  description = "Optional explicit name for the anomaly Feature Group."
  type        = string
  default     = null
}

variable "record_identifier_feature_name" {
  description = "Feature name used as the record identifier for both Feature Groups."
  type        = string
  default     = "feature_record_id"
}

variable "event_time_feature_name" {
  description = "Existing Gold feature column used as the Feature Store event-time field."
  type        = string
  default     = "interval_start_utc"
}

variable "tags" {
  description = "Standard tags applied to the Feature Group resources."
  type        = map(string)
  default     = {}
}
