"""AWS Glue job for Bronze-to-Silver energy and weather transformation.

This script is the first proper transformation layer in the project. It reads
raw Bronze JSON data registered in the Glue Data Catalog, reshapes the nested
payloads into row-based Silver datasets, and writes those curated outputs back
to Amazon S3 as Parquet.

Design notes
------------
- Bronze stays close to the upstream API responses.
- Silver becomes easier to query, join, and model against.
- The script keeps imports of Glue and Spark runtime libraries inside the job
  execution function so the module remains importable in local test
  environments that do not ship the AWS Glue runtime.

Examples
--------
The helper functions can be exercised locally without the full Glue runtime:

>>> build_s3_uri("dl-energyops-dev-creative-antelope", "silver/energy")
's3://dl-energyops-dev-creative-antelope/silver/energy/'
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING, Final, Sequence

if TYPE_CHECKING:
    from pyspark.sql import DataFrame

JOB_ARGUMENT_NAMES: Final[tuple[str, ...]] = (
    "JOB_NAME",
    "BRONZE_DATABASE_NAME",
    "ENERGY_TABLE_NAME",
    "WEATHER_TABLE_NAME",
    "LAKEHOUSE_BUCKET_NAME",
    "SILVER_ENERGY_PREFIX",
    "SILVER_WEATHER_PREFIX",
)


def normalise_prefix(prefix: str) -> str:
    """
    Remove leading and trailing slashes from an S3 prefix.

    Parameters
    ----------
    prefix : str
        Prefix such as `/silver/energy/`.

    Returns
    -------
    str
        Normalised prefix such as `silver/energy`.

    Examples
    --------
    >>> normalise_prefix("/silver/weather/")
    'silver/weather'
    """

    return prefix.strip("/")


def build_s3_uri(bucket_name: str, prefix: str) -> str:
    """
    Build a canonical S3 URI from a bucket name and object prefix.

    Parameters
    ----------
    bucket_name : str
        S3 bucket name.
    prefix : str
        S3 object prefix.

    Returns
    -------
    str
        Canonical S3 URI ending in a trailing slash.

    Examples
    --------
    >>> build_s3_uri("dl-energyops-dev-creative-antelope", "silver/energy")
    's3://dl-energyops-dev-creative-antelope/silver/energy/'
    """

    return f"s3://{bucket_name}/{normalise_prefix(prefix)}/"


def get_catalog_table_location(glue_client, database_name: str, table_name: str) -> str:
    """
    Resolve the S3 location for a Glue catalogue table.

    Parameters
    ----------
    glue_client : object
        Boto3 Glue client.
    database_name : str
        Glue database name.
    table_name : str
        Glue table name.

    Returns
    -------
    str
        S3 location registered against the Glue table.

    Examples
    --------
    >>> get_catalog_table_location(client, "bronze_db", "energy_table")  # doctest: +SKIP
    """

    table_response = glue_client.get_table(DatabaseName=database_name, Name=table_name)
    return table_response["Table"]["StorageDescriptor"]["Location"]


def read_catalog_json_dataset(spark, glue_client, database_name: str, table_name: str) -> "DataFrame":
    """
    Read a JSON dataset from the S3 location registered in the Glue catalogue.

    Parameters
    ----------
    spark : SparkSession
        Spark session used by the Glue job.
    glue_client : object
        Boto3 Glue client.
    database_name : str
        Glue database name.
    table_name : str
        Glue table name.

    Returns
    -------
    DataFrame
        Spark DataFrame parsed from the registered S3 location.

    Notes
    -----
    The Bronze raw payloads are written as pretty-printed multi-line JSON.
    Spark therefore needs the multiline JSON reader enabled rather than the
    default line-oriented JSON parsing behaviour.
    """

    dataset_location = get_catalog_table_location(glue_client, database_name, table_name)
    return (
        spark.read.option("multiLine", "true")
        .option("recursiveFileLookup", "true")
        .json(dataset_location)
    )


def run_job(argv: Sequence[str] | None = None) -> None:
    """
    Execute the Glue transformation job.

    Parameters
    ----------
    argv : Sequence[str] | None
        Optional argument vector used mainly for local testing hooks. AWS Glue
        ignores this and supplies job arguments through its own runtime.

    Examples
    --------
    >>> run_job()  # doctest: +SKIP
    """

    # Import Glue and Spark runtime libraries lazily so this module can still
    # be imported locally for syntax checks and small helper-function tests.
    import boto3
    from awsglue.context import GlueContext
    from awsglue.job import Job
    from awsglue.utils import getResolvedOptions
    from pyspark.context import SparkContext
    from pyspark.sql import functions as f

    spark_context = SparkContext.getOrCreate()
    glue_context = GlueContext(spark_context)
    spark = glue_context.spark_session
    resolved_args = getResolvedOptions(
        list(argv) if argv is not None else sys.argv,
        list(JOB_ARGUMENT_NAMES),
    )

    job = Job(glue_context)
    job.init(resolved_args["JOB_NAME"], resolved_args)

    bronze_database_name = resolved_args["BRONZE_DATABASE_NAME"]
    lakehouse_bucket_name = resolved_args["LAKEHOUSE_BUCKET_NAME"]
    silver_energy_path = build_s3_uri(lakehouse_bucket_name, resolved_args["SILVER_ENERGY_PREFIX"])
    silver_weather_path = build_s3_uri(lakehouse_bucket_name, resolved_args["SILVER_WEATHER_PREFIX"])

    glue_client = boto3.client("glue")

    # The Glue catalogue still defines the authoritative Bronze locations, but
    # the actual raw payload files are pretty-printed multi-line JSON. Reading
    # them through Spark's multiline JSON reader is more reliable than relying
    # on the catalogue source to infer the raw nested structure directly.
    bronze_energy_df = read_catalog_json_dataset(
        spark=spark,
        glue_client=glue_client,
        database_name=bronze_database_name,
        table_name=resolved_args["ENERGY_TABLE_NAME"],
    )

    bronze_weather_df = read_catalog_json_dataset(
        spark=spark,
        glue_client=glue_client,
        database_name=bronze_database_name,
        table_name=resolved_args["WEATHER_TABLE_NAME"],
    )

    energy_silver_df = transform_energy_bronze_to_silver(bronze_energy_df, f)
    weather_silver_df = transform_weather_bronze_to_silver(bronze_weather_df, f)

    # For the current scaffold, overwrite keeps the Silver outputs
    # deterministic and easy to inspect after repeated development runs.
    write_energy_silver(energy_silver_df, silver_energy_path)
    write_weather_silver(weather_silver_df, silver_weather_path)

    job.commit()


def transform_energy_bronze_to_silver(bronze_energy_df, f_module) -> "DataFrame":
    """
    Flatten Bronze Elexon payloads into one row per settlement interval.

    Parameters
    ----------
    bronze_energy_df : DataFrame
        Bronze energy DataFrame read from the Glue catalogue.
    f_module : module
        Spark SQL functions module, typically `pyspark.sql.functions`.

    Returns
    -------
    DataFrame
        Silver energy DataFrame with standardised timestamp and demand fields.

    Examples
    --------
    Each Bronze Elexon payload contains a `data` array. This helper explodes
    that array so the Silver output has one row per settlement interval.
    """

    exploded_records_df = bronze_energy_df.select(
        f_module.explode_outer("data").alias("record"),
        f_module.input_file_name().alias("source_object_path"),
    )

    return (
        exploded_records_df.where(f_module.col("record").isNotNull())
        .select(
            f_module.col("record.dataset").alias("dataset_name"),
            f_module.col("record.publishtime").alias("publish_time_utc_raw"),
            f_module.col("record.starttime").alias("interval_start_utc_raw"),
            f_module.col("record.settlementdate").alias("settlement_date_raw"),
            f_module.col("record.settlementperiod").cast("int").alias("settlement_period"),
            f_module.col("record.demand").cast("int").alias("demand_mw"),
            f_module.col("source_object_path"),
        )
        .withColumn("publish_time_utc", f_module.to_timestamp("publish_time_utc_raw"))
        .withColumn("interval_start_utc", f_module.to_timestamp("interval_start_utc_raw"))
        .withColumn("settlement_date", f_module.to_date("settlement_date_raw"))
        .withColumn("interval_end_utc", f_module.expr("interval_start_utc + INTERVAL 30 MINUTES"))
        .withColumn(
            "bronze_ingestion_date",
            f_module.regexp_extract("source_object_path", r"dt=(\d{4}-\d{2}-\d{2})", 1),
        )
        .drop("publish_time_utc_raw", "interval_start_utc_raw", "settlement_date_raw")
    )


def transform_weather_bronze_to_silver(bronze_weather_df, f_module) -> "DataFrame":
    """
    Flatten Bronze Open-Meteo payloads into one row per forecast timestamp.

    Parameters
    ----------
    bronze_weather_df : DataFrame
        Bronze weather DataFrame read from the Glue catalogue.
    f_module : module
        Spark SQL functions module, typically `pyspark.sql.functions`.

    Returns
    -------
    DataFrame
        Silver weather DataFrame with one row per hourly forecast point.

    Examples
    --------
    The helper zips the parallel weather arrays so that each forecast timestamp
    becomes one coherent Silver row.
    """

    # Open-Meteo returns parallel arrays inside the `hourly` struct. Zip those
    # arrays together first so each position becomes one coherent weather row.
    zipped_forecast_rows_df = bronze_weather_df.select(
        "latitude",
        "longitude",
        "timezone",
        "timezone_abbreviation",
        "elevation",
        f_module.arrays_zip(
            f_module.col("hourly.time"),
            f_module.col("hourly.temperature_2m"),
            f_module.col("hourly.relative_humidity_2m"),
            f_module.col("hourly.wind_speed_10m"),
        ).alias("forecast_rows"),
        f_module.input_file_name().alias("source_object_path"),
    )

    return (
        zipped_forecast_rows_df.select(
            "latitude",
            "longitude",
            "timezone",
            "timezone_abbreviation",
            "elevation",
            f_module.explode_outer("forecast_rows").alias("forecast_row"),
            "source_object_path",
        )
        .where(f_module.col("forecast_row").isNotNull())
        .select(
            "latitude",
            "longitude",
            "timezone",
            "timezone_abbreviation",
            "elevation",
            f_module.col("forecast_row.time").alias("forecast_time_local_raw"),
            f_module.col("forecast_row.temperature_2m").cast("double").alias("temperature_2m"),
            f_module.col("forecast_row.relative_humidity_2m")
            .cast("int")
            .alias("relative_humidity_2m"),
            f_module.col("forecast_row.wind_speed_10m").cast("double").alias("wind_speed_10m"),
            "source_object_path",
        )
        .withColumn("forecast_time_local", f_module.to_timestamp("forecast_time_local_raw"))
        .withColumn("forecast_date", f_module.to_date("forecast_time_local"))
        .withColumn(
            "bronze_ingestion_date",
            f_module.regexp_extract("source_object_path", r"dt=(\d{4}-\d{2}-\d{2})", 1),
        )
        .drop("forecast_time_local_raw")
    )


def write_energy_silver(energy_silver_df, output_path: str) -> None:
    """
    Write the Silver energy dataset to Parquet partitioned by settlement date.

    Parameters
    ----------
    energy_silver_df : DataFrame
        Transformed Silver energy DataFrame.
    output_path : str
        Target S3 URI for the Silver energy dataset.

    Examples
    --------
    >>> write_energy_silver(df, "s3://bucket/silver/energy/")  # doctest: +SKIP
    """

    energy_silver_df.write.mode("overwrite").partitionBy("settlement_date").parquet(output_path)


def write_weather_silver(weather_silver_df, output_path: str) -> None:
    """
    Write the Silver weather dataset to Parquet partitioned by forecast date.

    Parameters
    ----------
    weather_silver_df : DataFrame
        Transformed Silver weather DataFrame.
    output_path : str
        Target S3 URI for the Silver weather dataset.

    Examples
    --------
    >>> write_weather_silver(df, "s3://bucket/silver/weather/")  # doctest: +SKIP
    """

    weather_silver_df.write.mode("overwrite").partitionBy("forecast_date").parquet(output_path)


if __name__ == "__main__":
    run_job()
