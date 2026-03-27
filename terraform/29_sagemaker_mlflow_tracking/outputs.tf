output "mlflow_tracking_region" {
  value = var.aws_region
}

output "mlflow_tracking_server_name" {
  value = aws_sagemaker_mlflow_tracking_server.this.tracking_server_name
}

output "mlflow_tracking_server_arn" {
  value = aws_sagemaker_mlflow_tracking_server.this.arn
}

output "mlflow_tracking_server_url" {
  value = aws_sagemaker_mlflow_tracking_server.this.tracking_server_url
}

output "mlflow_tracking_server_artifact_store_uri" {
  value = local.artifact_store_uri
}

output "mlflow_tracking_server_role_arn" {
  value = var.sagemaker_role_arn
}

output "mlflow_tracking_server_version" {
  value = aws_sagemaker_mlflow_tracking_server.this.mlflow_version
}

output "mlflow_tracking_server_size" {
  value = aws_sagemaker_mlflow_tracking_server.this.tracking_server_size
}
