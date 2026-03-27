variable "aws_region" {
  description = "AWS region in which the SageMaker MLflow tracking server should be created."
  type        = string
}

variable "deployment_name" {
  description = "Shared deployment identifier produced by the project context module."
  type        = string
}

variable "artefact_bucket_name" {
  description = "Name of the S3 artefact bucket used by the tracking server for MLflow artefacts."
  type        = string
}

variable "sagemaker_role_arn" {
  description = "IAM role ARN used by the managed SageMaker MLflow tracking server."
  type        = string
}

variable "tracking_server_name" {
  description = "Optional explicit name for the managed SageMaker MLflow tracking server."
  type        = string
  default     = null
}

variable "artifact_store_prefix" {
  description = "Artefact-bucket prefix under which MLflow artefacts should be stored."
  type        = string
  default     = "mlflow"
}

variable "automatic_model_registration" {
  description = "Whether SageMaker should automatically register eligible MLflow model versions."
  type        = bool
  default     = false
}

variable "mlflow_version" {
  description = "Managed MLflow version used by the SageMaker tracking server."
  type        = string
  default     = null
  nullable    = true
}

variable "tracking_server_size" {
  description = "Managed SageMaker MLflow tracking server size."
  type        = string
  default     = "Small"
}

variable "weekly_maintenance_window_start" {
  description = "Optional weekly maintenance window in the form `DAY:HH:MM`."
  type        = string
  default     = "Sun:03:00"
}

variable "tags" {
  description = "Standard tags applied to the tracking server."
  type        = map(string)
  default     = {}
}
