variable "aws_region" {
  description = "AWS region in which the anomaly endpoint operates."
  type        = string
}

variable "deployment_name" {
  description = "Shared deployment identifier produced by the project context module."
  type        = string
}

variable "anomaly_endpoint_name" {
  description = "Stable SageMaker anomaly endpoint name to monitor and autoscale."
  type        = string
}

variable "anomaly_endpoint_variant_name" {
  description = "Production variant name within the anomaly endpoint."
  type        = string
}

variable "min_instance_count" {
  description = "Minimum number of endpoint instances maintained by autoscaling."
  type        = number
  default     = 1
}

variable "max_instance_count" {
  description = "Maximum number of endpoint instances allowed by autoscaling."
  type        = number
  default     = 3
}

variable "target_invocations_per_instance" {
  description = "Target invocations-per-instance used by SageMaker target-tracking autoscaling."
  type        = number
  default     = 50
}

variable "scale_in_cooldown_seconds" {
  description = "Cooldown applied after scale-in actions."
  type        = number
  default     = 300
}

variable "scale_out_cooldown_seconds" {
  description = "Cooldown applied after scale-out actions."
  type        = number
  default     = 120
}

variable "model_latency_threshold_microseconds" {
  description = "Average SageMaker model-latency threshold, in microseconds, that triggers the latency alarm."
  type        = number
  default     = 1000000
}

variable "latency_period_seconds" {
  description = "CloudWatch period used for the model-latency alarm."
  type        = number
  default     = 60
}

variable "latency_evaluation_periods" {
  description = "Number of CloudWatch periods used to evaluate the latency alarm."
  type        = number
  default     = 2
}

variable "invocation_5xx_threshold" {
  description = "Sum of 5XX invocation errors that triggers the corresponding alarm."
  type        = number
  default     = 1
}

variable "invocation_4xx_threshold" {
  description = "Sum of 4XX invocation errors that triggers the corresponding alarm."
  type        = number
  default     = 5
}

variable "error_period_seconds" {
  description = "CloudWatch period used for invocation error alarms."
  type        = number
  default     = 60
}

variable "error_evaluation_periods" {
  description = "Number of CloudWatch periods used to evaluate invocation error alarms."
  type        = number
  default     = 1
}

variable "alarm_actions" {
  description = "Optional alarm action ARNs, for example an SNS topic."
  type        = list(string)
  default     = []
}

variable "ok_actions" {
  description = "Optional OK action ARNs, for example an SNS topic."
  type        = list(string)
  default     = []
}
