variable "aws_region" {
  description = "AWS region in which anomaly autoencoder training assets should be staged."
  type        = string
}

variable "deployment_name" {
  description = "Shared deployment identifier produced by the project context module."
  type        = string
}

variable "kms_key_arn" {
  description = "KMS key ARN used to encrypt the uploaded source bundle and model outputs."
  type        = string
}

variable "artefact_bucket_name" {
  description = "Name of the S3 artefact bucket used for autoencoder training code and outputs."
  type        = string
}

variable "lakehouse_bucket_name" {
  description = "Name of the S3 lakehouse bucket that stores Gold anomaly features."
  type        = string
}

variable "sagemaker_role_arn" {
  description = "IAM role ARN assumed by the SageMaker autoencoder training job."
  type        = string
}

variable "anomaly_model_package_group_name" {
  description = "Name of the anomaly model package group used for registration."
  type        = string
}

variable "job_base_name" {
  description = "Optional deterministic base name used by the autoencoder runner before it appends a timestamp."
  type        = string
  default     = null
}

variable "source_bundle_key" {
  description = "Optional S3 object key under which the autoencoder source bundle should be uploaded."
  type        = string
  default     = null
}

variable "gold_anomaly_features_prefix" {
  description = "Lakehouse prefix under which the Gold anomaly-features dataset is stored."
  type        = string
  default     = "gold/anomaly_features"
}

variable "training_output_prefix" {
  description = "Artefact-bucket prefix under which SageMaker autoencoder training outputs should be written."
  type        = string
  default     = "sagemaker/anomaly_autoencoder_training/output"
}

variable "hidden_dim" {
  description = "Hidden width used by the dense autoencoder."
  type        = number
  default     = 32
}

variable "latent_dim" {
  description = "Latent bottleneck width used by the dense autoencoder."
  type        = number
  default     = 8
}

variable "max_epochs" {
  description = "Maximum training epochs for the dense autoencoder."
  type        = number
  default     = 40
}

variable "batch_size" {
  description = "Mini-batch size used during autoencoder training."
  type        = number
  default     = 64
}

variable "learning_rate" {
  description = "Optimizer learning rate used during autoencoder training."
  type        = number
  default     = 0.001
}

variable "score_quantile" {
  description = "Quantile of reconstruction scores used as the anomaly threshold."
  type        = number
  default     = 0.95
}

variable "pytorch_training_image_tag" {
  description = "PyTorch SageMaker training image tag used for the custom autoencoder training job."
  type        = string
  default     = "2.2.0-cpu-py310-ubuntu20.04-sagemaker"
}

variable "pytorch_inference_image_tag" {
  description = "PyTorch SageMaker inference image tag used for the registered autoencoder model package."
  type        = string
  default     = "2.2.0-cpu-py310-ubuntu20.04-sagemaker"
}

variable "pytorch_repository_account_id" {
  description = "Optional explicit ECR account ID for the SageMaker PyTorch images in this region."
  type        = string
  default     = null
}
