variable "aws_region" {
  description = "AWS region in which the SageMaker model registry resources should be created."
  type        = string
}

variable "deployment_name" {
  description = "Shared deployment identifier produced by the project context module."
  type        = string
}

variable "forecast_group_name" {
  description = "Optional explicit model package group name for forecasting models."
  type        = string
  default     = null
}

variable "anomaly_group_name" {
  description = "Optional explicit model package group name for anomaly models."
  type        = string
  default     = null
}

variable "forecast_group_description" {
  description = "Description applied to the forecasting model package group."
  type        = string
  default     = "Model registry group for energy-demand forecasting models."
}

variable "anomaly_group_description" {
  description = "Description applied to the anomaly model package group."
  type        = string
  default     = "Model registry group for anomaly detection models."
}

variable "tags" {
  description = "Standard tags applied to SageMaker model registry resources."
  type        = map(string)
  default     = {}
}
