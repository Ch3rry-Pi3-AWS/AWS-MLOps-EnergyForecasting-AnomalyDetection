"""Tests for SageMaker Feature Store helper functions."""

from energy_forecasting.ml.feature_store import (
    build_feature_record_id,
    build_feature_store_record,
    feature_value_as_string,
    format_feature_store_timestamp,
)


def test_feature_value_as_string_normalises_booleans_and_nulls():
    """Check that Feature Store values are rendered into API-safe strings."""

    assert feature_value_as_string(True) == "1"
    assert feature_value_as_string(False) == "0"
    assert feature_value_as_string(None) == ""


def test_build_feature_record_id_uses_dataset_and_interval_start():
    """Check that record identifiers stay deterministic across reingestion."""

    row = {
        "dataset_name": "forecast_features",
        "interval_start_utc": "2026-03-26T19:30:00+00:00",
    }

    assert build_feature_record_id(row) == "forecast_features|2026-03-26T19:30:00Z"


def test_format_feature_store_timestamp_adds_utc_suffix_when_missing():
    """Check that Feature Store event-time strings are rendered in SageMaker's accepted format."""

    assert format_feature_store_timestamp("2026-03-26T19:30:00") == "2026-03-26T19:30:00Z"


def test_build_feature_store_record_includes_record_id_and_gold_fields():
    """Check that a Gold row becomes a valid Feature Store record payload."""

    row = {
        "dataset_name": "forecast_features",
        "interval_start_utc": "2026-03-26T19:30:00",
        "settlement_period": 40,
        "temperature_2m": 8.9,
        "is_weekend": 0,
    }

    result = build_feature_store_record(row)

    assert result[0] == {
        "FeatureName": "feature_record_id",
        "ValueAsString": "forecast_features|2026-03-26T19:30:00Z",
    }
    assert {"FeatureName": "interval_start_utc", "ValueAsString": "2026-03-26T19:30:00Z"} in result
    assert {"FeatureName": "settlement_period", "ValueAsString": "40"} in result
    assert {"FeatureName": "temperature_2m", "ValueAsString": "8.9"} in result
    assert {"FeatureName": "is_weekend", "ValueAsString": "0"} in result
