variable "aws_region" {
  description = "AWS region in which TFT forecast training assets should be staged."
  type        = string
}

variable "deployment_name" {
  description = "Shared deployment identifier produced by the project context module."
  type        = string
}

variable "kms_key_arn" {
  description = "KMS key ARN used to encrypt the uploaded TFT source bundle and model outputs."
  type        = string
}

variable "artefact_bucket_name" {
  description = "Name of the S3 artefact bucket used for TFT training code and outputs."
  type        = string
}

variable "lakehouse_bucket_name" {
  description = "Name of the S3 lakehouse bucket that stores Gold forecast features."
  type        = string
}

variable "sagemaker_role_arn" {
  description = "IAM role ARN assumed by the SageMaker TFT training job."
  type        = string
}

variable "forecast_model_package_group_name" {
  description = "Name of the forecast model package group that trained TFT model versions should be registered into."
  type        = string
}

variable "job_base_name" {
  description = "Optional deterministic base name used by the TFT training runner before it appends a timestamp."
  type        = string
  default     = null
}

variable "source_bundle_key" {
  description = "Optional S3 object key under which the TFT source bundle should be uploaded."
  type        = string
  default     = null
}

variable "gold_forecast_features_prefix" {
  description = "Lakehouse prefix under which the Gold forecast-features dataset is stored."
  type        = string
  default     = "gold/forecast_features"
}

variable "training_output_prefix" {
  description = "Artefact-bucket prefix under which SageMaker TFT training outputs should be written."
  type        = string
  default     = "sagemaker/forecast_tft_training/output"
}

variable "context_length" {
  description = "Encoder context window length used by the TFT model."
  type        = number
  default     = 48
}

variable "prediction_length" {
  description = "Decoder prediction horizon length used by the TFT model."
  type        = number
  default     = 48
}

variable "max_epochs" {
  description = "Maximum number of training epochs for the TFT model."
  type        = number
  default     = 30
}

variable "batch_size" {
  description = "Mini-batch size used while training the TFT model."
  type        = number
  default     = 64
}

variable "hidden_size" {
  description = "Hidden size used inside the TFT architecture."
  type        = number
  default     = 32
}

variable "attention_head_size" {
  description = "Number of attention heads used by the TFT architecture."
  type        = number
  default     = 4
}

variable "hidden_continuous_size" {
  description = "Hidden size used for continuous variable processing inside the TFT architecture."
  type        = number
  default     = 16
}

variable "dropout" {
  description = "Dropout rate used during TFT training."
  type        = number
  default     = 0.1
}

variable "learning_rate" {
  description = "Optimizer learning rate used during TFT training."
  type        = number
  default     = 0.03
}

variable "pytorch_training_image_tag" {
  description = "PyTorch SageMaker training image tag used for the TFT custom training job."
  type        = string
  default     = "2.2.0-cpu-py310-ubuntu20.04-sagemaker"
}

variable "pytorch_inference_image_tag" {
  description = "PyTorch SageMaker inference image tag used for the registered TFT model package."
  type        = string
  default     = "2.2.0-cpu-py310-ubuntu20.04-sagemaker"
}

variable "pytorch_repository_account_id" {
  description = "Optional explicit ECR account ID for the SageMaker PyTorch images in this region."
  type        = string
  default     = null
}
