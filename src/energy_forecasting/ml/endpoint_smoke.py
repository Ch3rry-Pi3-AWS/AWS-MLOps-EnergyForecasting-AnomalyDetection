"""Helpers for live endpoint smoke tests and latest-Gold-row payloads."""

from __future__ import annotations

import io
import json
import math
import tarfile
from datetime import date, datetime
from typing import Any
from urllib.parse import urlparse

try:
    import pyarrow.parquet as pq
except ModuleNotFoundError:  # pragma: no cover - optional until latest-gold mode is used
    pq = None


PREFERRED_DYNAMIC_FEATURE_COLUMNS = [
    "settlement_period",
    "temperature_2m",
    "relative_humidity_2m",
    "wind_speed_10m",
    "interval_hour",
    "day_of_week",
    "month_of_year",
    "is_weekend",
]


def parse_s3_uri(s3_uri: str) -> tuple[str, str]:
    """Split an S3 URI into bucket and key-prefix components."""

    if not s3_uri.startswith("s3://"):
        raise ValueError(f"Expected an S3 URI, got: {s3_uri}")
    bucket_name, key_prefix = s3_uri.removeprefix("s3://").split("/", 1)
    return bucket_name, key_prefix


def parse_s3_uri_urlparse(s3_uri: str) -> tuple[str, str]:
    """Split an S3 URI into bucket and key components using URL parsing."""

    parsed = urlparse(s3_uri)
    if parsed.scheme != "s3" or not parsed.netloc:
        raise ValueError(f"Expected an S3 URI, got: {s3_uri}")
    return parsed.netloc, parsed.path.lstrip("/")


def normalise_json_value(value: Any) -> Any:
    """Convert Arrow or Python scalar values into JSON-safe payload values."""

    if value is None:
        return 0.0
    if isinstance(value, bool):
        return value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, float):
        return 0.0 if math.isnan(value) else value
    return value


def list_parquet_keys(s3_client, *, bucket_name: str, key_prefix: str) -> list[str]:
    """List every Parquet object stored under an S3 prefix."""

    paginator = s3_client.get_paginator("list_objects_v2")
    keys: list[str] = []
    for page in paginator.paginate(Bucket=bucket_name, Prefix=key_prefix):
        for item in page.get("Contents", []):
            key = item["Key"]
            if key.endswith(".parquet"):
                keys.append(key)
    return sorted(keys)


def load_parquet_rows(s3_client, *, dataset_s3_uri: str) -> list[dict[str, Any]]:
    """Load and return all Parquet rows under an S3 prefix."""

    if pq is None:
        raise RuntimeError(
            "pyarrow is required for latest-Gold-row payload generation. "
            "Install project dependencies and retry."
        )

    bucket_name, key_prefix = parse_s3_uri(dataset_s3_uri)
    parquet_keys = list_parquet_keys(s3_client, bucket_name=bucket_name, key_prefix=key_prefix)
    if not parquet_keys:
        raise FileNotFoundError(f"No Parquet files were found under {dataset_s3_uri}")

    rows: list[dict[str, Any]] = []
    for key in parquet_keys:
        body = s3_client.get_object(Bucket=bucket_name, Key=key)["Body"].read()
        table = pq.read_table(io.BytesIO(body))
        rows.extend(table.to_pylist())
    return rows


def extract_partition_value(key: str, marker: str = "settlement_date=") -> str:
    """Extract a partition value such as `settlement_date=YYYY-MM-DD` from an object key."""

    if marker not in key:
        return ""
    suffix = key.split(marker, 1)[1]
    return suffix.split("/", 1)[0]


def build_payload_record(row: dict[str, Any], *, excluded_columns: set[str]) -> dict[str, Any]:
    """Project a Parquet row into the numeric or boolean inference payload contract."""

    payload_record: dict[str, Any] = {}
    for key, value in row.items():
        if key in excluded_columns:
            continue
        normalized = normalise_json_value(value)
        if isinstance(normalized, (int, float, bool)):
            payload_record[key] = normalized
    return payload_record


def build_context(row: dict[str, Any], *, context_columns: list[str], fallback_partition: str) -> dict[str, str]:
    """Build a small context dictionary for terminal logging around a latest-row payload."""

    context: dict[str, str] = {}
    for column in context_columns:
        value = normalise_json_value(row.get(column, ""))
        if column == "settlement_date" and value == 0.0:
            value = fallback_partition
        context[column] = str(value)
    return context


def build_latest_row_payload_from_s3(
    s3_client,
    *,
    dataset_s3_uri: str,
    excluded_columns: set[str],
    context_columns: list[str],
) -> tuple[str, dict[str, Any]]:
    """Build an invocation payload from the latest Gold dataset row in S3."""

    bucket_name, key_prefix = parse_s3_uri(dataset_s3_uri)
    parquet_keys = list_parquet_keys(s3_client, bucket_name=bucket_name, key_prefix=key_prefix)
    if not parquet_keys:
        raise FileNotFoundError(f"No Parquet files were found under {dataset_s3_uri}")

    latest_row: dict[str, Any] | None = None
    latest_sort_value = ""
    latest_source_key = ""
    latest_partition = max(extract_partition_value(key) for key in parquet_keys)
    latest_partition_keys = [key for key in parquet_keys if extract_partition_value(key) == latest_partition]

    for key in latest_partition_keys:
        body = s3_client.get_object(Bucket=bucket_name, Key=key)["Body"].read()
        table = pq.read_table(io.BytesIO(body))
        for row in table.to_pylist():
            sort_value = str(normalise_json_value(row.get("interval_start_utc", "")))
            if sort_value > latest_sort_value:
                latest_sort_value = sort_value
                latest_row = row
                latest_source_key = key

    if latest_row is None:
        raise RuntimeError(f"Could not resolve the latest Gold row under {dataset_s3_uri}")

    payload_record = build_payload_record(latest_row, excluded_columns=excluded_columns)
    context = build_context(
        latest_row,
        context_columns=context_columns,
        fallback_partition=latest_partition,
    )
    context["source_s3_key"] = latest_source_key
    return json.dumps({"instances": [payload_record]}), context


def _forecast_row_sort_key(row: dict[str, Any]) -> tuple[str, float]:
    """Build a deterministic chronological sort key for forecast rows."""

    timestamp = str(normalise_json_value(row.get("interval_start_utc", "")))
    settlement_period = float(normalise_json_value(row.get("settlement_period", 0.0)))
    return timestamp, settlement_period


def build_latest_forecast_sequence_payload(
    s3_client,
    *,
    gold_input_s3_uri: str,
    required_rows: int,
) -> tuple[str, dict[str, Any]]:
    """Build a chronological TFT-style forecast payload from the latest forecast rows."""

    rows = [row for row in load_parquet_rows(s3_client, dataset_s3_uri=gold_input_s3_uri) if row.get("demand_mw") is not None]
    if len(rows) < required_rows:
        raise ValueError(
            f"Need at least {required_rows} Gold forecast rows to build a sequential payload, but only found {len(rows)}."
        )

    rows.sort(key=_forecast_row_sort_key)
    selected_rows = rows[-required_rows:]
    payload_rows = []
    for row in selected_rows:
        payload_row = build_payload_record(
            row,
            excluded_columns={"settlement_date", "publish_time_utc", "dataset_name"},
        )
        payload_row["demand_mw"] = float(normalise_json_value(row.get("demand_mw")))
        payload_rows.append(payload_row)

    latest_row = selected_rows[-1]
    context = build_context(
        latest_row,
        context_columns=["interval_start_utc", "interval_end_utc", "settlement_date", "publish_time_utc"],
        fallback_partition=str(normalise_json_value(latest_row.get("settlement_date", ""))),
    )
    context["history_rows"] = str(required_rows)
    return json.dumps({"instances": payload_rows}), context


def build_latest_forecast_deepar_payload(
    s3_client,
    *,
    gold_input_s3_uri: str,
    feature_columns: list[str],
    context_length: int,
    prediction_length: int,
) -> tuple[str, dict[str, Any]]:
    """Build a DeepAR payload from the latest forecast rows plus synthetic future covariates."""

    required_rows = context_length + prediction_length
    rows = [row for row in load_parquet_rows(s3_client, dataset_s3_uri=gold_input_s3_uri) if row.get("demand_mw") is not None]
    if len(rows) < required_rows:
        raise ValueError(
            f"Need at least {required_rows} Gold forecast rows to build a DeepAR payload, but only found {len(rows)}."
        )

    rows.sort(key=_forecast_row_sort_key)
    selected_rows = rows[-required_rows:]
    history_rows = selected_rows[:context_length]
    future_rows = selected_rows[context_length:]

    target = [float(normalise_json_value(row.get("demand_mw"))) for row in history_rows]
    dynamic_feat: list[list[float]] = []
    for column in feature_columns:
        history_values = [float(normalise_json_value(row.get(column, 0.0))) for row in history_rows]
        future_values = [float(normalise_json_value(row.get(column, history_values[-1] if history_values else 0.0))) for row in future_rows]
        dynamic_feat.append(history_values + future_values)

    start = str(normalise_json_value(history_rows[0].get("interval_start_utc", ""))).replace("T", " ").replace("+00:00", "")
    payload = {
        "instances": [
            {
                "start": start,
                "target": target,
                "dynamic_feat": dynamic_feat,
            }
        ],
        "configuration": {
            "num_samples": 100,
            "output_types": ["mean"],
        },
    }
    latest_row = selected_rows[-1]
    context = build_context(
        latest_row,
        context_columns=["interval_start_utc", "interval_end_utc", "settlement_date", "publish_time_utc"],
        fallback_partition=str(normalise_json_value(latest_row.get("settlement_date", ""))),
    )
    context["context_length"] = str(context_length)
    context["prediction_length"] = str(prediction_length)
    return json.dumps(payload), context


def validate_forecast_response(body: str) -> dict[str, Any]:
    """Validate the forecast endpoint response contract and return the parsed payload."""

    payload = json.loads(body)
    predictions = payload.get("predictions")
    if not isinstance(predictions, list) or not predictions:
        raise ValueError("Forecast endpoint response must contain a non-empty 'predictions' list.")
    first = predictions[0]
    if isinstance(first, (int, float)):
        return payload
    if isinstance(first, dict):
        mean_values = first.get("mean")
        if not isinstance(mean_values, list) or not mean_values:
            raise ValueError("Forecast prediction objects must contain a non-empty 'mean' list.")
        if not all(isinstance(value, (int, float)) for value in mean_values):
            raise ValueError("Forecast prediction-object 'mean' values must be numeric.")
        return payload
    raise ValueError("Forecast endpoint predictions must be numeric or DeepAR-style prediction objects.")
    return payload


def validate_anomaly_response(body: str) -> dict[str, Any]:
    """Validate the anomaly endpoint response contract and return the parsed payload."""

    payload = json.loads(body)
    predictions = payload.get("predictions")
    if not isinstance(predictions, list) or not predictions:
        raise ValueError("Anomaly endpoint response must contain a non-empty 'predictions' list.")
    first = predictions[0]
    if not isinstance(first, dict):
        raise ValueError("Anomaly endpoint predictions must be objects.")
    if "anomaly_score" not in first or "is_anomaly" not in first:
        raise ValueError("Anomaly endpoint prediction objects must contain 'anomaly_score' and 'is_anomaly'.")
    if not isinstance(first["anomaly_score"], (int, float)):
        raise ValueError("Anomaly endpoint 'anomaly_score' must be numeric.")
    if not isinstance(first["is_anomaly"], bool):
        raise ValueError("Anomaly endpoint 'is_anomaly' must be boolean.")
    return payload


def read_evaluation_json_from_tarball(s3_client, *, bucket_name: str, object_key: str) -> dict[str, Any]:
    """Extract `evaluation.json` from a SageMaker output tarball stored in S3."""

    response = s3_client.get_object(Bucket=bucket_name, Key=object_key)
    data = response["Body"].read()
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
        for member in archive.getmembers():
            if member.name.endswith("evaluation.json"):
                extracted = archive.extractfile(member)
                if extracted is None:
                    continue
                return json.loads(extracted.read().decode("utf-8"))
    raise FileNotFoundError(f"No evaluation.json file was found inside s3://{bucket_name}/{object_key}")


def load_training_metrics_from_model_package(
    sagemaker_client,
    s3_client,
    *,
    model_package_arn: str,
) -> tuple[str, dict[str, Any]]:
    """Load model-package metadata and training metrics for a deployed SageMaker package."""

    package_description = sagemaker_client.describe_model_package(ModelPackageName=model_package_arn)
    metadata = package_description.get("CustomerMetadataProperties", {})
    training_job_name = metadata.get("training_job_name")
    if not training_job_name:
        return metadata.get("forecast_algorithm", "baseline"), {}

    training_description = sagemaker_client.describe_training_job(TrainingJobName=training_job_name)
    bucket_name, model_artifact_key = parse_s3_uri_urlparse(training_description["ModelArtifacts"]["S3ModelArtifacts"])
    output_prefix = model_artifact_key.rsplit("/", 1)[0] + "/"
    response = s3_client.list_objects_v2(Bucket=bucket_name, Prefix=output_prefix)
    for item in response.get("Contents", []):
        key = item["Key"]
        if key.endswith("evaluation.json"):
            body = s3_client.get_object(Bucket=bucket_name, Key=key)["Body"].read().decode("utf-8")
            return metadata.get("forecast_algorithm", "baseline"), json.loads(body)
        if key.endswith("output.tar.gz"):
            return metadata.get("forecast_algorithm", "baseline"), read_evaluation_json_from_tarball(
                s3_client,
                bucket_name=bucket_name,
                object_key=key,
            )
    return metadata.get("forecast_algorithm", "baseline"), {}


def get_deployed_model_package_arn(sagemaker_client, *, endpoint_name: str) -> str | None:
    """Resolve the model package ARN currently backing a stable SageMaker endpoint."""

    endpoint = sagemaker_client.describe_endpoint(EndpointName=endpoint_name)
    endpoint_config = sagemaker_client.describe_endpoint_config(
        EndpointConfigName=endpoint["EndpointConfigName"]
    )
    model_name = endpoint_config["ProductionVariants"][0]["ModelName"]
    model = sagemaker_client.describe_model(ModelName=model_name)
    primary_container = model.get("PrimaryContainer", {})
    return primary_container.get("ModelPackageName")
