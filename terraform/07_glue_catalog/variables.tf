variable "aws_region" {
  description = "AWS region in which the Glue catalogue resources should be created."
  type        = string
}

variable "deployment_name" {
  description = "Shared deployment identifier produced by the project context module."
  type        = string
}

variable "lakehouse_bucket_name" {
  description = "Name of the S3 lakehouse bucket that stores Bronze raw data and manifests."
  type        = string
}

variable "bronze_raw_prefix" {
  description = "Prefix under which raw Bronze source payloads are written."
  type        = string
  default     = "bronze/raw"
}

variable "bronze_ingest_prefix" {
  description = "Prefix under which Bronze ingestion manifests are written."
  type        = string
  default     = "bronze/ingestion-manifests"
}

variable "database_name" {
  description = "Optional explicit name for the Glue database."
  type        = string
  default     = null
}

variable "database_description" {
  description = "Description applied to the Bronze Glue database."
  type        = string
  default     = "Glue catalogue database for Bronze energy, weather, and ingestion-manifest datasets."
}

variable "energy_table_name" {
  description = "Optional explicit name for the Bronze energy table."
  type        = string
  default     = null
}

variable "energy_table_description" {
  description = "Description applied to the Bronze raw energy table."
  type        = string
  default     = "External table for raw Elexon ITSDO payloads landed in the Bronze layer."
}

variable "weather_table_name" {
  description = "Optional explicit name for the Bronze weather table."
  type        = string
  default     = null
}

variable "weather_table_description" {
  description = "Description applied to the Bronze raw weather table."
  type        = string
  default     = "External table for raw Open-Meteo forecast payloads landed in the Bronze layer."
}

variable "manifest_table_name" {
  description = "Optional explicit name for the Bronze ingestion manifest table."
  type        = string
  default     = null
}

variable "manifest_table_description" {
  description = "Description applied to the Bronze ingestion manifest table."
  type        = string
  default     = "External table for Lambda ingestion manifests and operational run metadata."
}

variable "tags" {
  description = "Standard tags applied to the Glue catalogue resources."
  type        = map(string)
  default     = {}
}
