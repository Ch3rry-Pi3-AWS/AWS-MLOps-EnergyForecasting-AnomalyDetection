terraform {
  required_version = ">= 1.5"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

locals {
  # Keep the Glue job and script object names predictable so later modules,
  # docs, and operations can refer to them consistently.
  job_name          = var.job_name != null ? var.job_name : "glue-bronze-silver-${var.deployment_name}"
  script_object_key = var.script_object_key != null ? var.script_object_key : "glue/jobs/bronze_to_silver.py"
  script_local_path = abspath("${path.module}/../../glue/jobs/bronze_to_silver.py")
  temp_dir_uri      = "s3://${var.artefact_bucket_name}/${trim(var.temp_prefix, "/")}/"
}

# Upload the job script into the artefact bucket so Glue can execute the exact
# repository version associated with this Terraform deployment.
resource "aws_s3_object" "glue_job_script" {
  bucket                 = var.artefact_bucket_name
  key                    = local.script_object_key
  source                 = local.script_local_path
  etag                   = filemd5(local.script_local_path)
  content_type           = "text/x-python"
  server_side_encryption = "aws:kms"
  kms_key_id             = var.kms_key_arn

  tags = merge(
    var.tags,
    {
      Name      = local.script_object_key
      Component = "glue-job-script"
    }
  )
}

# Create the first transformation job that reads Bronze catalogue tables,
# flattens the raw structures, and writes Silver Parquet datasets.
resource "aws_glue_job" "main" {
  name              = local.job_name
  description       = var.description
  role_arn          = var.glue_role_arn
  glue_version      = var.glue_version
  worker_type       = var.worker_type
  number_of_workers = var.number_of_workers
  max_retries       = var.max_retries
  timeout           = var.timeout

  command {
    name            = "glueetl"
    script_location = "s3://${var.artefact_bucket_name}/${aws_s3_object.glue_job_script.key}"
    python_version  = "3"
  }

  execution_property {
    max_concurrent_runs = var.max_concurrent_runs
  }

  default_arguments = {
    "--job-language"          = "python"
    "--enable-metrics"        = "true"
    "--enable-job-insights"   = "true"
    "--job-bookmark-option"   = "job-bookmark-disable"
    "--TempDir"               = local.temp_dir_uri
    "--BRONZE_DATABASE_NAME"  = var.glue_database_name
    "--ENERGY_TABLE_NAME"     = var.energy_table_name
    "--WEATHER_TABLE_NAME"    = var.weather_table_name
    "--LAKEHOUSE_BUCKET_NAME" = var.lakehouse_bucket_name
    "--SILVER_ENERGY_PREFIX"  = var.silver_energy_prefix
    "--SILVER_WEATHER_PREFIX" = var.silver_weather_prefix
  }

  tags = merge(
    var.tags,
    {
      Name      = local.job_name
      DataLayer = "silver"
      Component = "glue-job"
    }
  )

  depends_on = [aws_s3_object.glue_job_script]
}
