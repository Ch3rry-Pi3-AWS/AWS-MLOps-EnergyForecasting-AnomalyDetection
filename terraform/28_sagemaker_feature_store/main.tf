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
  forecast_feature_group_name = var.forecast_feature_group_name != null ? var.forecast_feature_group_name : "${var.deployment_name}-forecast-feature-group"
  anomaly_feature_group_name  = var.anomaly_feature_group_name != null ? var.anomaly_feature_group_name : "${var.deployment_name}-anomaly-feature-group"

  feature_store_root_s3_uri     = "s3://${var.lakehouse_bucket_name}/${trim(var.feature_store_prefix, "/")}"
  forecast_offline_store_s3_uri = "${local.feature_store_root_s3_uri}/forecast"
  anomaly_offline_store_s3_uri  = "${local.feature_store_root_s3_uri}/anomaly"
  forecast_gold_input_s3_uri    = "s3://${var.lakehouse_bucket_name}/${trim(var.gold_forecast_features_prefix, "/")}/"
  anomaly_gold_input_s3_uri     = "s3://${var.lakehouse_bucket_name}/${trim(var.gold_anomaly_features_prefix, "/")}/"
  record_id_feature_definition  = [{ feature_name = var.record_identifier_feature_name, feature_type = "String" }]

  forecast_feature_definitions = [
    { feature_name = "dataset_name", feature_type = "String" },
    { feature_name = "publish_time_utc", feature_type = "String" },
    { feature_name = "interval_start_utc", feature_type = "String" },
    { feature_name = "interval_end_utc", feature_type = "String" },
    { feature_name = "settlement_period", feature_type = "Integral" },
    { feature_name = "settlement_date", feature_type = "String" },
    { feature_name = "demand_mw", feature_type = "Fractional" },
    { feature_name = "bronze_ingestion_date", feature_type = "String" },
    { feature_name = "weather_timestamp", feature_type = "String" },
    { feature_name = "temperature_2m", feature_type = "Fractional" },
    { feature_name = "relative_humidity_2m", feature_type = "Fractional" },
    { feature_name = "wind_speed_10m", feature_type = "Fractional" },
    { feature_name = "latitude", feature_type = "Fractional" },
    { feature_name = "longitude", feature_type = "Fractional" },
    { feature_name = "timezone", feature_type = "String" },
    { feature_name = "interval_hour", feature_type = "Integral" },
    { feature_name = "day_of_week", feature_type = "Integral" },
    { feature_name = "month_of_year", feature_type = "Integral" },
    { feature_name = "is_weekend", feature_type = "Integral" },
    { feature_name = "lag_1_demand_mw", feature_type = "Fractional" },
    { feature_name = "lag_2_demand_mw", feature_type = "Fractional" },
    { feature_name = "lag_48_demand_mw", feature_type = "Fractional" },
    { feature_name = "rolling_mean_48_demand_mw", feature_type = "Fractional" },
    { feature_name = "rolling_min_48_demand_mw", feature_type = "Fractional" },
    { feature_name = "rolling_max_48_demand_mw", feature_type = "Fractional" },
  ]

  anomaly_feature_definitions = concat(
    local.forecast_feature_definitions,
    [
      { feature_name = "rolling_stddev_48_demand_mw", feature_type = "Fractional" },
      { feature_name = "demand_minus_rolling_mean_mw", feature_type = "Fractional" },
      { feature_name = "demand_to_rolling_mean_ratio", feature_type = "Fractional" },
      { feature_name = "rolling_z_score", feature_type = "Fractional" },
    ]
  )
}

resource "aws_sagemaker_feature_group" "forecast" {
  feature_group_name             = local.forecast_feature_group_name
  record_identifier_feature_name = var.record_identifier_feature_name
  event_time_feature_name        = var.event_time_feature_name
  role_arn                       = var.sagemaker_role_arn

  offline_store_config {
    disable_glue_table_creation = false

    s3_storage_config {
      s3_uri     = local.forecast_offline_store_s3_uri
      kms_key_id = var.kms_key_arn
    }
  }

  dynamic "feature_definition" {
    for_each = concat(local.record_id_feature_definition, local.forecast_feature_definitions)
    content {
      feature_name = feature_definition.value.feature_name
      feature_type = feature_definition.value.feature_type
    }
  }

  tags = var.tags
}

resource "aws_sagemaker_feature_group" "anomaly" {
  feature_group_name             = local.anomaly_feature_group_name
  record_identifier_feature_name = var.record_identifier_feature_name
  event_time_feature_name        = var.event_time_feature_name
  role_arn                       = var.sagemaker_role_arn

  offline_store_config {
    disable_glue_table_creation = false

    s3_storage_config {
      s3_uri     = local.anomaly_offline_store_s3_uri
      kms_key_id = var.kms_key_arn
    }
  }

  dynamic "feature_definition" {
    for_each = concat(local.record_id_feature_definition, local.anomaly_feature_definitions)
    content {
      feature_name = feature_definition.value.feature_name
      feature_type = feature_definition.value.feature_type
    }
  }

  tags = var.tags
}
