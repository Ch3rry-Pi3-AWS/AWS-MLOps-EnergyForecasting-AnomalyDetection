"""Tests for SageMaker naming helpers used by the ML scaffold.

Examples
--------
Run just this test module locally:

>>> # pytest tests/test_ml_pipeline.py
"""

from energy_forecasting.ml.pipeline import (
    build_model_package_group_name,
    build_training_job_name,
)


def test_build_training_job_name_is_deterministic():
    """Check that training job names follow the documented naming convention."""

    result = build_training_job_name("energyops-dev-creative-antelope", "forecast-xgb")

    assert result == "energyops-dev-creative-antelope-forecast-xgb-train"


def test_build_model_package_group_name_is_deterministic():
    """Check that model registry group names follow the documented convention."""

    result = build_model_package_group_name("energyops-dev-creative-antelope", "forecast")

    assert result == "energyops-dev-creative-antelope-forecast-registry"
