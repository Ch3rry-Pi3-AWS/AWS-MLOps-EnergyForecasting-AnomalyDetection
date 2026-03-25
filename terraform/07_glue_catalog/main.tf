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
  # Build readable catalogue object names from the shared deployment identity
  # unless the caller explicitly overrides them.
  database_name = var.database_name != null ? var.database_name : replace("glue_bronze_${var.deployment_name}", "-", "_")
  table_names = {
    energy   = var.energy_table_name != null ? var.energy_table_name : replace("bronze_energy_${var.deployment_name}", "-", "_")
    weather  = var.weather_table_name != null ? var.weather_table_name : replace("bronze_weather_${var.deployment_name}", "-", "_")
    manifest = var.manifest_table_name != null ? var.manifest_table_name : replace("bronze_manifest_${var.deployment_name}", "-", "_")
  }

  locations = {
    energy   = "s3://${var.lakehouse_bucket_name}/${trim(var.bronze_raw_prefix, "/")}/energy/"
    weather  = "s3://${var.lakehouse_bucket_name}/${trim(var.bronze_raw_prefix, "/")}/weather/"
    manifest = "s3://${var.lakehouse_bucket_name}/${trim(var.bronze_ingest_prefix, "/")}/manifest/"
  }
}

resource "aws_glue_catalog_database" "bronze" {
  name        = local.database_name
  description = var.database_description

  tags = merge(
    var.tags,
    {
      Name      = local.database_name
      DataLayer = "bronze"
      Component = "glue-catalog"
    }
  )
}

# Register the raw energy landing zone so Glue and Athena-compatible tools can
# discover the source schema without hardcoded S3 paths.
resource "aws_glue_catalog_table" "energy" {
  name          = local.table_names["energy"]
  database_name = aws_glue_catalog_database.bronze.name
  table_type    = "EXTERNAL_TABLE"
  description   = var.energy_table_description

  parameters = {
    EXTERNAL             = "TRUE"
    classification       = "json"
    "projection.enabled" = "false"
    "typeOfData"         = "file"
    "compressionType"    = "none"
  }

  storage_descriptor {
    location      = local.locations["energy"]
    input_format  = "org.apache.hadoop.mapred.TextInputFormat"
    output_format = "org.apache.hadoop.hive.ql.io.HiveIgnoreKeyTextOutputFormat"

    ser_de_info {
      serialization_library = "org.openx.data.jsonserde.JsonSerDe"
    }

    columns {
      name = "data"
      type = "array<struct<dataset:string,publishtime:string,starttime:string,settlementdate:string,settlementperiod:int,demand:int>>"
    }
  }
}

# The weather table keeps the nested hourly forecast arrays intact. Later
# Bronze-to-Silver jobs can normalise the arrays into one row per timestamp.
resource "aws_glue_catalog_table" "weather" {
  name          = local.table_names["weather"]
  database_name = aws_glue_catalog_database.bronze.name
  table_type    = "EXTERNAL_TABLE"
  description   = var.weather_table_description

  parameters = {
    EXTERNAL             = "TRUE"
    classification       = "json"
    "projection.enabled" = "false"
    "typeOfData"         = "file"
    "compressionType"    = "none"
  }

  storage_descriptor {
    location      = local.locations["weather"]
    input_format  = "org.apache.hadoop.mapred.TextInputFormat"
    output_format = "org.apache.hadoop.hive.ql.io.HiveIgnoreKeyTextOutputFormat"

    ser_de_info {
      serialization_library = "org.openx.data.jsonserde.JsonSerDe"
    }

    columns {
      name = "latitude"
      type = "double"
    }

    columns {
      name = "longitude"
      type = "double"
    }

    columns {
      name = "generationtime_ms"
      type = "double"
    }

    columns {
      name = "utc_offset_seconds"
      type = "int"
    }

    columns {
      name = "timezone"
      type = "string"
    }

    columns {
      name = "timezone_abbreviation"
      type = "string"
    }

    columns {
      name = "elevation"
      type = "double"
    }

    columns {
      name = "hourly_units"
      type = "struct<time:string,temperature_2m:string,relative_humidity_2m:string,wind_speed_10m:string>"
    }

    columns {
      name = "hourly"
      type = "struct<time:array<string>,temperature_2m:array<double>,relative_humidity_2m:array<int>,wind_speed_10m:array<double>>"
    }
  }
}

# The manifest table captures operational metadata about each Lambda run so
# ingestion health can be inspected without opening raw payload files.
resource "aws_glue_catalog_table" "manifest" {
  name          = local.table_names["manifest"]
  database_name = aws_glue_catalog_database.bronze.name
  table_type    = "EXTERNAL_TABLE"
  description   = var.manifest_table_description

  parameters = {
    EXTERNAL             = "TRUE"
    classification       = "json"
    "projection.enabled" = "false"
    "typeOfData"         = "file"
    "compressionType"    = "none"
  }

  storage_descriptor {
    location      = local.locations["manifest"]
    input_format  = "org.apache.hadoop.mapred.TextInputFormat"
    output_format = "org.apache.hadoop.hive.ql.io.HiveIgnoreKeyTextOutputFormat"

    ser_de_info {
      serialization_library = "org.openx.data.jsonserde.JsonSerDe"
    }

    columns {
      name = "request_id"
      type = "string"
    }

    columns {
      name = "event_time_utc"
      type = "string"
    }

    columns {
      name = "deployment_name"
      type = "string"
    }

    columns {
      name = "environment"
      type = "string"
    }

    columns {
      name = "status"
      type = "string"
    }

    columns {
      name = "sources"
      type = "struct<energy:struct<base_url:string,path:string>,weather:struct<base_url:string,path:string,latitude:string,longitude:string,hourly_fields:string,timezone:string>>"
    }

    columns {
      name = "event"
      type = "struct<source:string,trigger:string>"
    }

    columns {
      name = "outputs"
      type = "struct<energy:struct<source_name:string,s3_key:string,record_count:int>,weather:struct<source_name:string,s3_key:string,hourly_timestamp_count:int,forecast_start_time:string,forecast_end_time:string>>"
    }

    columns {
      name = "error"
      type = "struct<type:string,message:string>"
    }
  }
}
