# Surface the job identifiers so future schedulers, workflows, or monitoring
# modules can trigger and inspect the transformation job directly.
output "glue_job_name" {
  value = aws_glue_job.main.name
}

output "glue_job_arn" {
  value = aws_glue_job.main.arn
}

output "glue_job_script_s3_uri" {
  value = "s3://${var.artefact_bucket_name}/${aws_s3_object.glue_job_script.key}"
}
