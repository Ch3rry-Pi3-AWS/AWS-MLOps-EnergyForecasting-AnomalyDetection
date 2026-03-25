"""Evaluation helpers for SageMaker model-package promotion decisions.

This module keeps the promotion logic separate from the runner scripts so the
same threshold checks can be unit tested locally and reused by later
automation, for example SageMaker Pipelines or CI-triggered model reviews.

Examples
--------
>>> build_evaluation_report_key(
...     "sagemaker/model_evaluation/forecast",
...     "forecast",
...     3,
...     "20260325203000",
... )
'sagemaker/model_evaluation/forecast/forecast/model_package_version=3/20260325203000.json'
>>> evaluate_forecast_metrics(
...     {"mae": 1200.0, "rmse": 1800.0, "r2": 0.71, "training_rows": 72},
...     {"min_training_rows": 48, "max_mae": 5000.0, "max_rmse": 7000.0, "min_r2": 0.0},
... )["passed"]
True
>>> evaluate_anomaly_metrics(
...     {"training_rows": 96, "detected_anomaly_rows": 4},
...     {"min_training_rows": 48, "min_anomaly_rate": 0.01, "max_anomaly_rate": 0.2},
... )["derived_metrics"]["anomaly_rate"]
0.041666666666666664
"""

from __future__ import annotations

from collections.abc import Mapping


def normalise_s3_prefix(prefix: str) -> str:
    """
    Remove leading and trailing slashes from an S3 key prefix.

    Parameters
    ----------
    prefix : str
        Raw prefix value that may include surrounding slashes.

    Returns
    -------
    str
        Prefix without leading or trailing slash characters.
    """

    return prefix.strip("/")


def build_evaluation_report_key(
    report_prefix: str,
    model_family: str,
    model_package_version: int,
    timestamp_suffix: str,
) -> str:
    """
    Build a deterministic S3 key for an evaluation report.

    Parameters
    ----------
    report_prefix : str
        Base prefix under which evaluation reports are written.
    model_family : str
        Model family identifier, for example `forecast` or `anomaly`.
    model_package_version : int
        Numeric SageMaker model package version being evaluated.
    timestamp_suffix : str
        Timestamp used to keep repeated evaluations distinct.

    Returns
    -------
    str
        S3 key for the JSON evaluation report.
    """

    prefix = normalise_s3_prefix(report_prefix)
    return (
        f"{prefix}/{model_family}/model_package_version={model_package_version}/"
        f"{timestamp_suffix}.json"
    )


def _build_check(
    *,
    name: str,
    observed: float,
    comparator: str,
    target: float,
    passed: bool,
) -> dict[str, object]:
    """Create a uniform threshold-check record for evaluation reports."""

    return {
        "name": name,
        "observed": observed,
        "comparator": comparator,
        "target": target,
        "passed": passed,
    }


def evaluate_forecast_metrics(
    metrics: Mapping[str, object],
    thresholds: Mapping[str, float],
) -> dict[str, object]:
    """
    Evaluate forecast metrics against promotion thresholds.

    Parameters
    ----------
    metrics : Mapping[str, object]
        Training metrics loaded from `evaluation.json`.
    thresholds : Mapping[str, float]
        Threshold values used to determine promotion readiness.

    Returns
    -------
    dict[str, object]
        Structured evaluation summary containing individual checks and an
        overall `passed` flag.
    """

    training_rows = int(metrics.get("training_rows", 0))
    mae = float(metrics["mae"])
    rmse = float(metrics["rmse"])
    r2 = float(metrics["r2"])

    checks = [
        _build_check(
            name="min_training_rows",
            observed=float(training_rows),
            comparator=">=",
            target=float(thresholds["min_training_rows"]),
            passed=training_rows >= int(thresholds["min_training_rows"]),
        ),
        _build_check(
            name="max_mae",
            observed=mae,
            comparator="<=",
            target=float(thresholds["max_mae"]),
            passed=mae <= float(thresholds["max_mae"]),
        ),
        _build_check(
            name="max_rmse",
            observed=rmse,
            comparator="<=",
            target=float(thresholds["max_rmse"]),
            passed=rmse <= float(thresholds["max_rmse"]),
        ),
        _build_check(
            name="min_r2",
            observed=r2,
            comparator=">=",
            target=float(thresholds["min_r2"]),
            passed=r2 >= float(thresholds["min_r2"]),
        ),
    ]

    return {
        "passed": all(check["passed"] for check in checks),
        "checks": checks,
        "derived_metrics": {},
    }


def evaluate_anomaly_metrics(
    metrics: Mapping[str, object],
    thresholds: Mapping[str, float],
) -> dict[str, object]:
    """
    Evaluate anomaly metrics against lightweight promotion thresholds.

    Parameters
    ----------
    metrics : Mapping[str, object]
        Training metrics loaded from `evaluation.json`.
    thresholds : Mapping[str, float]
        Threshold values used to determine promotion readiness.

    Returns
    -------
    dict[str, object]
        Structured evaluation summary containing individual checks, derived
        anomaly rate, and an overall `passed` flag.
    """

    training_rows = int(metrics.get("training_rows", 0))
    detected_anomaly_rows = int(metrics.get("detected_anomaly_rows", 0))
    anomaly_rate = 0.0 if training_rows == 0 else detected_anomaly_rows / training_rows

    checks = [
        _build_check(
            name="min_training_rows",
            observed=float(training_rows),
            comparator=">=",
            target=float(thresholds["min_training_rows"]),
            passed=training_rows >= int(thresholds["min_training_rows"]),
        ),
        _build_check(
            name="min_anomaly_rate",
            observed=anomaly_rate,
            comparator=">=",
            target=float(thresholds["min_anomaly_rate"]),
            passed=anomaly_rate >= float(thresholds["min_anomaly_rate"]),
        ),
        _build_check(
            name="max_anomaly_rate",
            observed=anomaly_rate,
            comparator="<=",
            target=float(thresholds["max_anomaly_rate"]),
            passed=anomaly_rate <= float(thresholds["max_anomaly_rate"]),
        ),
    ]

    return {
        "passed": all(check["passed"] for check in checks),
        "checks": checks,
        "derived_metrics": {
            "anomaly_rate": anomaly_rate,
        },
    }
