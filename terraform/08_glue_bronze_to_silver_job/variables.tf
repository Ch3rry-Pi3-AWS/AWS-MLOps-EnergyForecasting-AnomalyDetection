variable "aws_region" {
  description = "AWS region in which the Glue Bronze-to-Silver job should be created."
  type        = string
}

variable "deployment_name" {
  description = "Shared deployment identifier produced by the project context module."
  type        = string
}

variable "kms_key_arn" {
  description = "KMS key ARN used to encrypt the uploaded Glue job script."
  type        = string
}

variable "glue_role_arn" {
  description = "IAM role ARN assumed by the AWS Glue job."
  type        = string
}

variable "lakehouse_bucket_name" {
  description = "Name of the S3 lakehouse bucket containing Bronze and Silver data."
  type        = string
}

variable "artefact_bucket_name" {
  description = "Name of the S3 artefact bucket used to store Glue job scripts and temporary files."
  type        = string
}

variable "glue_database_name" {
  description = "Glue database name containing the Bronze catalogue tables."
  type        = string
}

variable "energy_table_name" {
  description = "Glue table name for Bronze raw energy payloads."
  type        = string
}

variable "weather_table_name" {
  description = "Glue table name for Bronze raw weather payloads."
  type        = string
}

variable "job_name" {
  description = "Optional explicit name for the Glue job."
  type        = string
  default     = null
}

variable "description" {
  description = "Description applied to the Glue Bronze-to-Silver job."
  type        = string
  default     = "Glue job that flattens Bronze energy and weather payloads into Silver Parquet datasets."
}

variable "script_object_key" {
  description = "Optional object key used when uploading the Glue job script to the artefact bucket."
  type        = string
  default     = null
}

variable "temp_prefix" {
  description = "Artefact-bucket prefix used by Glue for temporary files."
  type        = string
  default     = "glue/temp/bronze_to_silver"
}

variable "silver_energy_prefix" {
  description = "Lakehouse prefix under which the Silver energy dataset should be written."
  type        = string
  default     = "silver/energy"
}

variable "silver_weather_prefix" {
  description = "Lakehouse prefix under which the Silver weather dataset should be written."
  type        = string
  default     = "silver/weather"
}

variable "glue_version" {
  description = "AWS Glue runtime version used by the Bronze-to-Silver job."
  type        = string
  default     = "4.0"
}

variable "worker_type" {
  description = "Worker type used by the Glue job."
  type        = string
  default     = "G.1X"
}

variable "number_of_workers" {
  description = "Number of workers allocated to the Glue job."
  type        = number
  default     = 2
}

variable "max_retries" {
  description = "Maximum number of automatic retries for the Glue job."
  type        = number
  default     = 0
}

variable "timeout" {
  description = "Glue job timeout in minutes."
  type        = number
  default     = 30
}

variable "max_concurrent_runs" {
  description = "Maximum number of concurrent Glue job runs."
  type        = number
  default     = 1
}

variable "tags" {
  description = "Standard tags applied to the Glue job and uploaded script object."
  type        = map(string)
  default     = {}
}
