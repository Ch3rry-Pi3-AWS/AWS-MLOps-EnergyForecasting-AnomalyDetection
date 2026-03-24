variable "aws_region" {
  type        = string
  description = "AWS region used by downstream modules"
  default     = "eu-west-2"
}

variable "environment" {
  type        = string
  description = "Environment name such as dev or prod"
  default     = "dev"
}

variable "project_name" {
  type        = string
  description = "Friendly project name used in tags"
  default     = "Real-Time Energy Forecasting and Anomaly Detection"
}

variable "project_slug" {
  type        = string
  description = "Lowercase slug used in tags and configuration"
  default     = "energy-forecast"
}

variable "resource_prefix" {
  type        = string
  description = "Prefix used to build resource names before the generated suffix"
  default     = "energyops"
}

variable "owner" {
  type        = string
  description = "Owner tag"
  default     = "portfolio"
}

variable "cost_centre" {
  type        = string
  description = "Cost centre tag"
  default     = "mlops-lab"
}

variable "extra_tags" {
  type        = map(string)
  description = "Optional extra tags merged into the standard tag set"
  default     = {}
}

