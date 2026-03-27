"""Helpers for SageMaker Feature Store record building and Gold backfills."""

from __future__ import annotations

import math
from datetime import date, datetime
from typing import Any

from energy_forecasting.ml.endpoint_smoke import load_parquet_rows, normalise_json_value

TIMESTAMP_FEATURE_NAMES = {
    "publish_time_utc",
    "interval_start_utc",
    "interval_end_utc",
    "weather_timestamp",
}


def feature_value_as_string(value: Any) -> str:
    """Render a Gold feature value into SageMaker Feature Store string form."""

    if value is None:
        return ""
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, float):
        return "0.0" if math.isnan(value) else str(value)
    return str(value)


def format_feature_store_timestamp(value: Any) -> str:
    """Render a timestamp-like value into a SageMaker Feature Store ISO-8601 string."""

    normalised = normalise_json_value(value)
    if isinstance(normalised, datetime):
        text = normalised.isoformat()
    else:
        text = str(normalised).strip()

    if not text:
        return text

    if text.endswith("Z"):
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    else:
        if "T" not in text and " " in text:
            text = text.replace(" ", "T", 1)
        if "+" not in text and not text.endswith("Z"):
            text = f"{text}Z"
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))

    return parsed.strftime("%Y-%m-%dT%H:%M:%SZ")


def build_feature_record_id(row: dict[str, Any]) -> str:
    """Build a deterministic feature-store record identifier from a Gold row."""

    dataset_name = str(normalise_json_value(row.get("dataset_name", "unknown")))
    interval_start_utc = format_feature_store_timestamp(row.get("interval_start_utc", ""))
    return f"{dataset_name}|{interval_start_utc}"


def feature_row_sort_key(row: dict[str, Any]) -> tuple[str, float]:
    """Build a chronological sort key for Gold feature rows."""

    timestamp = str(normalise_json_value(row.get("interval_start_utc", "")))
    settlement_period = float(normalise_json_value(row.get("settlement_period", 0.0)))
    return timestamp, settlement_period


def load_gold_feature_rows(
    s3_client,
    *,
    dataset_s3_uri: str,
    max_records: int | None = None,
) -> list[dict[str, Any]]:
    """Load Gold feature rows from S3, sort them, and optionally keep the latest slice."""

    rows = load_parquet_rows(s3_client, dataset_s3_uri=dataset_s3_uri)
    rows.sort(key=feature_row_sort_key)
    if max_records is not None:
        return rows[-max_records:]
    return rows


def build_feature_store_record(
    row: dict[str, Any],
    *,
    record_identifier_feature_name: str = "feature_record_id",
) -> list[dict[str, str]]:
    """Convert a Gold row into a SageMaker Feature Store `PutRecord` payload."""

    record = [
        {
            "FeatureName": record_identifier_feature_name,
            "ValueAsString": build_feature_record_id(row),
        }
    ]

    for feature_name, raw_value in row.items():
        if feature_name in TIMESTAMP_FEATURE_NAMES:
            value_as_string = format_feature_store_timestamp(raw_value)
        else:
            normalised = normalise_json_value(raw_value)
            value_as_string = feature_value_as_string(normalised)
        record.append(
            {
                "FeatureName": feature_name,
                "ValueAsString": value_as_string,
            }
        )

    return record
