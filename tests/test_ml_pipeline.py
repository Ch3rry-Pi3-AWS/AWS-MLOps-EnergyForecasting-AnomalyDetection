"""Tests for SageMaker naming helpers used by the ML scaffold.

Examples
--------
Run just this test module locally:

>>> # pytest tests/test_ml_pipeline.py
"""

from energy_forecasting.ml.pipeline import (
    build_model_package_group_name,
    build_timestamped_sagemaker_name,
    build_training_job_name,
    build_timestamped_training_job_name,
)


def test_build_training_job_name_is_deterministic():
    """Check that training job names follow the documented naming convention."""

    result = build_training_job_name("energyops-dev-creative-antelope", "forecast-xgb")

    assert result == "energyops-dev-creative-antelope-forecast-xgb-train"


def test_build_model_package_group_name_is_deterministic():
    """Check that model registry group names follow the documented convention."""

    result = build_model_package_group_name("energyops-dev-creative-antelope", "forecast")

    assert result == "energyops-dev-creative-antelope-forecast-registry"


def test_build_timestamped_training_job_name_appends_run_suffix():
    """Check that training job run names stay unique while keeping the base name readable."""

    result = build_timestamped_training_job_name(
        "energyops-dev-creative-antelope-forecast-sklearn-train",
        "20260325113000",
    )

    assert result == "energyops-dev-creative-antelope-forecast-sklearn-20260325113000"
    assert len(result) <= 63


def test_build_timestamped_training_job_name_truncates_long_base_name():
    """Check that long base names are trimmed to SageMaker's job-name limit."""

    result = build_timestamped_training_job_name(
        "energyops-dev-creative-antelope-forecast-sklearn-train",
        "20260325145458",
    )

    assert result == "energyops-dev-creative-antelope-forecast-sklearn-20260325145458"
    assert len(result) == 63


def test_build_timestamped_sagemaker_name_truncates_for_endpoint_style_names():
    """Check that generic SageMaker names are safely truncated with a unique suffix."""

    result = build_timestamped_sagemaker_name(
        "energyops-dev-creative-antelope-forecast-endpoint-config",
        "20260325160000",
    )

    assert result == "energyops-dev-creative-antelope-forecast-endpoin-20260325160000"
    assert len(result) == 63
