"""Tests for endpoint smoke-test helpers and response validation."""

from energy_forecasting.ml.endpoint_smoke import (
    build_context,
    build_payload_record,
    validate_anomaly_response,
    validate_forecast_response,
)


def test_build_payload_record_keeps_numeric_and_boolean_values_only():
    """Check that latest-row payload projection keeps only serving-safe values."""

    row = {
        "interval_hour": 18,
        "temperature_2m": 11.2,
        "is_weekend": False,
        "interval_start_utc": "2026-03-26T18:00:00+00:00",
        "dataset_name": "energy",
    }

    result = build_payload_record(
        row,
        excluded_columns={"interval_start_utc", "dataset_name"},
    )

    assert result == {
        "interval_hour": 18,
        "temperature_2m": 11.2,
        "is_weekend": False,
    }


def test_build_context_uses_fallback_partition_for_missing_settlement_date():
    """Check that latest-row context stays readable even when partition metadata is needed."""

    row = {
        "interval_start_utc": "2026-03-26T18:00:00+00:00",
        "interval_end_utc": "2026-03-26T18:30:00+00:00",
        "settlement_date": None,
    }

    result = build_context(
        row,
        context_columns=["interval_start_utc", "interval_end_utc", "settlement_date"],
        fallback_partition="2026-03-26",
    )

    assert result == {
        "interval_start_utc": "2026-03-26T18:00:00+00:00",
        "interval_end_utc": "2026-03-26T18:30:00+00:00",
        "settlement_date": "2026-03-26",
    }


def test_validate_forecast_response_accepts_non_empty_numeric_predictions():
    """Check the forecast smoke validator against the hosted response contract."""

    result = validate_forecast_response('{"predictions": [30871.804249141638]}')

    assert result["predictions"][0] == 30871.804249141638


def test_validate_forecast_response_accepts_deepar_prediction_objects():
    """Check the forecast smoke validator against the built-in DeepAR response contract."""

    result = validate_forecast_response(
        '{"predictions": [{"mean": [30100.0, 30200.5], "quantiles": {"0.5": [30100.0, 30200.5]}}]}'
    )

    assert result["predictions"][0]["mean"] == [30100.0, 30200.5]


def test_validate_anomaly_response_accepts_score_and_flag_objects():
    """Check the anomaly smoke validator against the hosted response contract."""

    result = validate_anomaly_response(
        '{"predictions": [{"anomaly_score": -0.55, "is_anomaly": false}]}'
    )

    assert result["predictions"][0] == {
        "anomaly_score": -0.55,
        "is_anomaly": False,
    }
