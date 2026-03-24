# Core deployment location used by downstream AWS modules.
variable "aws_region" {
  type        = string
  description = "AWS region used by downstream modules"
  default     = "eu-west-2"
}

# Environment name is embedded into resource names and tags so dev and prod
# stay visually distinct.
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

# The slug is a compact project identifier intended for structured metadata.
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

# Ownership and cost metadata are kept explicit because they are usually
# among the first tags required in real AWS environments.
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
