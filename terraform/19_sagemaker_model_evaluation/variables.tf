variable "aws_region" {
  description = "AWS region in which evaluation reports and model metadata are managed."
  type        = string
}

variable "deployment_name" {
  description = "Shared deployment identifier produced by the project context module."
  type        = string
}

variable "artefact_bucket_name" {
  description = "Artefact bucket used to store model-evaluation reports."
  type        = string
}

variable "kms_key_arn" {
  description = "KMS key ARN used to encrypt uploaded evaluation reports."
  type        = string
}

variable "forecast_model_package_group_name" {
  description = "Forecast model package group whose packages will be evaluated for promotion."
  type        = string
}

variable "anomaly_model_package_group_name" {
  description = "Anomaly model package group whose packages will be evaluated for promotion."
  type        = string
}

variable "forecast_report_prefix" {
  description = "Optional artefact-bucket prefix for forecast evaluation reports."
  type        = string
  default     = null
}

variable "anomaly_report_prefix" {
  description = "Optional artefact-bucket prefix for anomaly evaluation reports."
  type        = string
  default     = null
}

variable "forecast_min_training_rows" {
  description = "Minimum forecast training rows required before automatic promotion is considered."
  type        = number
  default     = 48
}

variable "forecast_max_mae" {
  description = "Maximum MAE allowed for a forecast package to pass automated evaluation."
  type        = number
  default     = 5000
}

variable "forecast_max_rmse" {
  description = "Maximum RMSE allowed for a forecast package to pass automated evaluation."
  type        = number
  default     = 7000
}

variable "forecast_min_r2" {
  description = "Minimum R-squared required for a forecast package to pass automated evaluation."
  type        = number
  default     = 0
}

variable "anomaly_min_training_rows" {
  description = "Minimum anomaly training rows required before automatic promotion is considered."
  type        = number
  default     = 48
}

variable "anomaly_min_anomaly_rate" {
  description = "Minimum anomaly rate expected from the baseline detector before auto-promotion is considered."
  type        = number
  default     = 0.01
}

variable "anomaly_max_anomaly_rate" {
  description = "Maximum anomaly rate tolerated before the anomaly detector is treated as too noisy."
  type        = number
  default     = 0.20
}
