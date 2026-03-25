"""AWS Glue job for Silver-to-Gold feature engineering.

This script creates the first model-ready Gold layer in the project. It reads
curated Silver energy and weather datasets from Amazon S3, aligns them on a
shared hourly view, engineers a small set of forecasting and anomaly-oriented
features, and writes the resulting Gold outputs back to S3 as Parquet.

Design notes
------------
- Silver remains close to source-aligned cleaned data.
- Gold introduces joined, time-aware features intended for modelling.
- The first Gold implementation deliberately stays simple and explicit rather
  than trying to solve every forecasting nuance in one pass.
- Glue and Spark imports remain inside `run_job` so local tests can import the
  helper functions without the AWS Glue runtime installed.

Examples
--------
The path helpers can be exercised locally:

>>> build_s3_uri("dl-energyops-dev-creative-antelope", "gold/forecast_features")
's3://dl-energyops-dev-creative-antelope/gold/forecast_features/'
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING, Final, Sequence

if TYPE_CHECKING:
    from pyspark.sql import DataFrame

JOB_ARGUMENT_NAMES: Final[tuple[str, ...]] = (
    "JOB_NAME",
    "LAKEHOUSE_BUCKET_NAME",
    "SILVER_ENERGY_PREFIX",
    "SILVER_WEATHER_PREFIX",
    "GOLD_FORECAST_FEATURES_PREFIX",
    "GOLD_ANOMALY_FEATURES_PREFIX",
)


def normalise_prefix(prefix: str) -> str:
    """
    Remove leading and trailing slashes from an S3 prefix.

    Parameters
    ----------
    prefix : str
        Prefix such as `/gold/forecast_features/`.

    Returns
    -------
    str
        Normalised prefix such as `gold/forecast_features`.

    Examples
    --------
    >>> normalise_prefix("/gold/anomaly_features/")
    'gold/anomaly_features'
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
    >>> build_s3_uri("dl-energyops-dev-creative-antelope", "gold/forecast_features")
    's3://dl-energyops-dev-creative-antelope/gold/forecast_features/'
    """

    return f"s3://{bucket_name}/{normalise_prefix(prefix)}/"


def read_parquet_dataset(spark, dataset_uri: str) -> "DataFrame":
    """
    Read a Parquet dataset from S3.

    Parameters
    ----------
    spark : SparkSession
        Spark session used by the Glue job.
    dataset_uri : str
        Canonical S3 URI pointing at a Parquet dataset.

    Returns
    -------
    DataFrame
        Spark DataFrame loaded from the given Parquet dataset.

    Examples
    --------
    >>> read_parquet_dataset(spark, "s3://bucket/silver/energy/")  # doctest: +SKIP
    """

    return spark.read.parquet(dataset_uri)


def run_job(argv: Sequence[str] | None = None) -> None:
    """
    Execute the Glue transformation job.

    Parameters
    ----------
    argv : Sequence[str] | None
        Optional argument vector used mainly for local testing hooks. AWS Glue
        supplies job arguments through its own runtime.

    Examples
    --------
    >>> run_job()  # doctest: +SKIP
    """

    # Import Glue and Spark lazily so helper-function tests can run locally
    # without the AWS Glue runtime.
    from awsglue.context import GlueContext
    from awsglue.job import Job
    from awsglue.utils import getResolvedOptions
    from pyspark.context import SparkContext
    from pyspark.sql import Window
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

    lakehouse_bucket_name = resolved_args["LAKEHOUSE_BUCKET_NAME"]
    silver_energy_path = build_s3_uri(lakehouse_bucket_name, resolved_args["SILVER_ENERGY_PREFIX"])
    silver_weather_path = build_s3_uri(lakehouse_bucket_name, resolved_args["SILVER_WEATHER_PREFIX"])
    gold_forecast_path = build_s3_uri(
        lakehouse_bucket_name,
        resolved_args["GOLD_FORECAST_FEATURES_PREFIX"],
    )
    gold_anomaly_path = build_s3_uri(
        lakehouse_bucket_name,
        resolved_args["GOLD_ANOMALY_FEATURES_PREFIX"],
    )

    silver_energy_df = read_parquet_dataset(spark, silver_energy_path)
    silver_weather_df = read_parquet_dataset(spark, silver_weather_path)

    forecast_features_df = transform_silver_to_forecast_features(
        silver_energy_df=silver_energy_df,
        silver_weather_df=silver_weather_df,
        f_module=f,
        window_module=Window,
    )
    anomaly_features_df = transform_forecast_to_anomaly_features(
        forecast_features_df=forecast_features_df,
        f_module=f,
        window_module=Window,
    )

    # Overwrite keeps repeated development runs easy to reason about while the
    # Gold schema is still evolving.
    write_forecast_features(forecast_features_df, gold_forecast_path)
    write_anomaly_features(anomaly_features_df, gold_anomaly_path)

    job.commit()


def transform_silver_to_forecast_features(
    silver_energy_df,
    silver_weather_df,
    f_module,
    window_module,
) -> "DataFrame":
    """
    Join Silver energy and weather datasets into Gold forecasting features.

    Parameters
    ----------
    silver_energy_df : DataFrame
        Curated Silver energy dataset.
    silver_weather_df : DataFrame
        Curated Silver weather dataset.
    f_module : module
        Spark SQL functions module, typically `pyspark.sql.functions`.
    window_module : module
        Spark SQL window module, typically `pyspark.sql.Window`.

    Returns
    -------
    DataFrame
        Gold forecasting feature dataset.

    Notes
    -----
    The current join strategy truncates the half-hour energy interval start to
    the hour and joins to the hourly weather timestamp. That intentionally
    favours simplicity and inspectability for the first Gold layer.

    Examples
    --------
    The output includes:

    - calendar features such as hour, day-of-week, and weekend flag
    - lagged demand features
    - rolling demand averages
    - aligned weather covariates
    """

    energy_window = window_module.orderBy("interval_start_utc")

    # Weather arrives hourly while energy is half-hourly. The current Gold
    # layer aligns them by hour so both half-hour demand rows within the same
    # hour inherit the same weather snapshot.
    weather_hourly_df = silver_weather_df.select(
        f_module.col("forecast_time_local").alias("weather_timestamp"),
        f_module.date_trunc("hour", "forecast_time_local").alias("weather_join_hour"),
        "temperature_2m",
        "relative_humidity_2m",
        "wind_speed_10m",
        "latitude",
        "longitude",
        "timezone",
    )

    joined_features_df = (
        silver_energy_df.select(
            "dataset_name",
            "publish_time_utc",
            "interval_start_utc",
            "interval_end_utc",
            "settlement_period",
            "settlement_date",
            "demand_mw",
            "bronze_ingestion_date",
        )
        .withColumn("weather_join_hour", f_module.date_trunc("hour", "interval_start_utc"))
        .join(weather_hourly_df, on="weather_join_hour", how="left")
    )

    return (
        joined_features_df.withColumn("interval_hour", f_module.hour("interval_start_utc"))
        .withColumn("day_of_week", f_module.dayofweek("interval_start_utc"))
        .withColumn("month_of_year", f_module.month("interval_start_utc"))
        .withColumn(
            "is_weekend",
            f_module.when(f_module.col("day_of_week").isin(1, 7), f_module.lit(1)).otherwise(
                f_module.lit(0)
            ),
        )
        .withColumn("lag_1_demand_mw", f_module.lag("demand_mw", 1).over(energy_window))
        .withColumn("lag_2_demand_mw", f_module.lag("demand_mw", 2).over(energy_window))
        .withColumn("lag_48_demand_mw", f_module.lag("demand_mw", 48).over(energy_window))
        .withColumn(
            "rolling_mean_48_demand_mw",
            f_module.avg("demand_mw").over(energy_window.rowsBetween(-47, 0)),
        )
        .withColumn(
            "rolling_min_48_demand_mw",
            f_module.min("demand_mw").over(energy_window.rowsBetween(-47, 0)),
        )
        .withColumn(
            "rolling_max_48_demand_mw",
            f_module.max("demand_mw").over(energy_window.rowsBetween(-47, 0)),
        )
        .drop("weather_join_hour")
    )


def transform_forecast_to_anomaly_features(
    forecast_features_df,
    f_module,
    window_module,
) -> "DataFrame":
    """
    Extend Gold forecasting features with anomaly-oriented diagnostics.

    Parameters
    ----------
    forecast_features_df : DataFrame
        Gold forecasting feature dataset.
    f_module : module
        Spark SQL functions module, typically `pyspark.sql.functions`.
    window_module : module
        Spark SQL window module, typically `pyspark.sql.Window`.

    Returns
    -------
    DataFrame
        Gold anomaly feature dataset.

    Examples
    --------
    The anomaly dataset includes:

    - short-window rolling mean and standard deviation
    - deviation from the recent rolling mean
    - a simple z-score style normalised signal
    """

    anomaly_window = window_module.orderBy("interval_start_utc").rowsBetween(-47, 0)

    anomaly_base_df = (
        forecast_features_df.withColumn(
            "rolling_stddev_48_demand_mw",
            f_module.stddev_pop("demand_mw").over(anomaly_window),
        )
        .withColumn(
            "demand_minus_rolling_mean_mw",
            f_module.col("demand_mw") - f_module.col("rolling_mean_48_demand_mw"),
        )
        .withColumn(
            "demand_to_rolling_mean_ratio",
            f_module.when(
                f_module.col("rolling_mean_48_demand_mw").isNotNull()
                & (f_module.col("rolling_mean_48_demand_mw") != 0),
                f_module.col("demand_mw") / f_module.col("rolling_mean_48_demand_mw"),
            ),
        )
    )

    return anomaly_base_df.withColumn(
        "rolling_z_score",
        f_module.when(
            f_module.col("rolling_stddev_48_demand_mw").isNotNull()
            & (f_module.col("rolling_stddev_48_demand_mw") != 0),
            f_module.col("demand_minus_rolling_mean_mw") / f_module.col("rolling_stddev_48_demand_mw"),
        ),
    )


def write_forecast_features(forecast_features_df, output_path: str) -> None:
    """
    Write the Gold forecasting feature dataset to Parquet.

    Parameters
    ----------
    forecast_features_df : DataFrame
        Gold forecasting features.
    output_path : str
        Target S3 URI for the forecast-feature dataset.

    Examples
    --------
    >>> write_forecast_features(df, "s3://bucket/gold/forecast_features/")  # doctest: +SKIP
    """

    forecast_features_df.write.mode("overwrite").partitionBy("settlement_date").parquet(output_path)


def write_anomaly_features(anomaly_features_df, output_path: str) -> None:
    """
    Write the Gold anomaly feature dataset to Parquet.

    Parameters
    ----------
    anomaly_features_df : DataFrame
        Gold anomaly-oriented features.
    output_path : str
        Target S3 URI for the anomaly-feature dataset.

    Examples
    --------
    >>> write_anomaly_features(df, "s3://bucket/gold/anomaly_features/")  # doctest: +SKIP
    """

    anomaly_features_df.write.mode("overwrite").partitionBy("settlement_date").parquet(output_path)


if __name__ == "__main__":
    run_job()
