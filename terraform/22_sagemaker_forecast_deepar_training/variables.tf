variable "aws_region" {
  description = "AWS region in which DeepAR forecast training assets should be staged."
  type        = string
}

variable "deployment_name" {
  description = "Shared deployment identifier produced by the project context module."
  type        = string
}

variable "kms_key_arn" {
  description = "KMS key ARN used to encrypt staged DeepAR inputs and evaluation outputs."
  type        = string
}

variable "artefact_bucket_name" {
  description = "Name of the S3 artefact bucket used to store DeepAR inputs, training outputs, and evaluation reports."
  type        = string
}

variable "lakehouse_bucket_name" {
  description = "Name of the S3 lakehouse bucket that stores Gold forecast features."
  type        = string
}

variable "sagemaker_role_arn" {
  description = "IAM role ARN assumed by the SageMaker DeepAR training job."
  type        = string
}

variable "forecast_model_package_group_name" {
  description = "Name of the forecast model package group that trained DeepAR model versions should be registered into."
  type        = string
}

variable "job_base_name" {
  description = "Optional deterministic base name used by the DeepAR training runner before it appends a timestamp."
  type        = string
  default     = null
}

variable "gold_forecast_features_prefix" {
  description = "Lakehouse prefix under which the Gold forecast-features dataset is stored."
  type        = string
  default     = "gold/forecast_features"
}

variable "prepared_input_prefix" {
  description = "Artefact-bucket prefix under which the runner uploads DeepAR-formatted train and test datasets."
  type        = string
  default     = "sagemaker/forecast_deepar_training/input"
}

variable "training_output_prefix" {
  description = "Artefact-bucket prefix under which SageMaker DeepAR training outputs should be written."
  type        = string
  default     = "sagemaker/forecast_deepar_training/output"
}

variable "evaluation_output_prefix" {
  description = "Artefact-bucket prefix under which temporary DeepAR evaluation-request and response artefacts should be written."
  type        = string
  default     = "sagemaker/forecast_deepar_training/evaluation"
}

variable "prediction_length" {
  description = "DeepAR forecast horizon in time steps."
  type        = number
  default     = 48
}

variable "context_length" {
  description = "DeepAR context window length in time steps."
  type        = number
  default     = 48
}

variable "time_freq" {
  description = "Time-series frequency string passed to the DeepAR algorithm."
  type        = string
  default     = "30min"
}

variable "epochs" {
  description = "Maximum number of DeepAR training epochs."
  type        = number
  default     = 50
}

variable "num_layers" {
  description = "Number of recurrent layers used by DeepAR."
  type        = number
  default     = 2
}

variable "num_cells" {
  description = "Number of recurrent cells per DeepAR layer."
  type        = number
  default     = 40
}

variable "mini_batch_size" {
  description = "Mini-batch size used during DeepAR training."
  type        = number
  default     = 32
}

variable "likelihood" {
  description = "Likelihood function used by DeepAR."
  type        = string
  default     = "gaussian"
}

variable "deepar_image_tag" {
  description = "Built-in DeepAR algorithm image tag."
  type        = string
  default     = "1"
}

variable "deepar_repository_account_id" {
  description = "Optional explicit ECR account ID for the SageMaker DeepAR built-in algorithm image in this region."
  type        = string
  default     = null
}
