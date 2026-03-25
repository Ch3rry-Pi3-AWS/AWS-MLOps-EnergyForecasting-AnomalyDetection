"""Tests for model-evaluation helpers used in promotion decisions.

Examples
--------
Run just this test module locally:

>>> # pytest tests/test_model_evaluation.py
"""

from energy_forecasting.ml.evaluation import (
    build_evaluation_report_key,
    evaluate_anomaly_metrics,
    evaluate_forecast_metrics,
    normalise_s3_prefix,
)


def test_normalise_s3_prefix_trims_surrounding_slashes():
    """Check that report prefixes stay consistent regardless of user formatting."""

    assert normalise_s3_prefix("/sagemaker/model_evaluation/forecast/") == (
        "sagemaker/model_evaluation/forecast"
    )


def test_build_evaluation_report_key_is_deterministic():
    """Check that evaluation reports land under predictable versioned prefixes."""

    result = build_evaluation_report_key(
        "sagemaker/model_evaluation/forecast",
        "forecast",
        3,
        "20260325203000",
    )

    assert result == (
        "sagemaker/model_evaluation/forecast/forecast/"
        "model_package_version=3/20260325203000.json"
    )


def test_evaluate_forecast_metrics_passes_when_all_thresholds_are_met():
    """Check that a healthy forecast metrics bundle produces a passing recommendation."""

    result = evaluate_forecast_metrics(
        {
            "mae": 1200.0,
            "rmse": 1800.0,
            "r2": 0.71,
            "training_rows": 96,
        },
        {
            "min_training_rows": 48,
            "max_mae": 5000.0,
            "max_rmse": 7000.0,
            "min_r2": 0.0,
        },
    )

    assert result["passed"] is True
    assert all(check["passed"] for check in result["checks"])


def test_evaluate_forecast_metrics_fails_when_r2_and_volume_are_too_weak():
    """Check that poor forecast metrics do not get a passing recommendation."""

    result = evaluate_forecast_metrics(
        {
            "mae": 5200.0,
            "rmse": 8100.0,
            "r2": -0.3,
            "training_rows": 12,
        },
        {
            "min_training_rows": 48,
            "max_mae": 5000.0,
            "max_rmse": 7000.0,
            "min_r2": 0.0,
        },
    )

    assert result["passed"] is False
    assert [check["name"] for check in result["checks"] if not check["passed"]] == [
        "min_training_rows",
        "max_mae",
        "max_rmse",
        "min_r2",
    ]


def test_evaluate_anomaly_metrics_computes_anomaly_rate_and_passes():
    """Check that anomaly evaluation derives the anomaly rate correctly."""

    result = evaluate_anomaly_metrics(
        {
            "training_rows": 96,
            "detected_anomaly_rows": 4,
        },
        {
            "min_training_rows": 48,
            "min_anomaly_rate": 0.01,
            "max_anomaly_rate": 0.20,
        },
    )

    assert result["passed"] is True
    assert result["derived_metrics"]["anomaly_rate"] == 4 / 96


def test_evaluate_anomaly_metrics_fails_when_dataset_is_too_small_and_rate_is_extreme():
    """Check that anomaly promotion fails when bootstrap metrics look unreliable."""

    result = evaluate_anomaly_metrics(
        {
            "training_rows": 12,
            "detected_anomaly_rows": 10,
        },
        {
            "min_training_rows": 48,
            "min_anomaly_rate": 0.01,
            "max_anomaly_rate": 0.20,
        },
    )

    assert result["passed"] is False
    assert [check["name"] for check in result["checks"] if not check["passed"]] == [
        "min_training_rows",
        "max_anomaly_rate",
    ]
