"""Tests for the shared environment-driven settings helper.

Examples
--------
Run just this test module locally:

>>> # pytest tests/test_settings.py
"""

from energy_forecasting.config.settings import Settings


def test_settings_from_env_defaults(monkeypatch):
    """Confirm that `Settings.from_env` falls back to documented defaults."""

    monkeypatch.delenv("PROJECT_NAME", raising=False)
    monkeypatch.delenv("PROJECT_ENV", raising=False)
    monkeypatch.delenv("AWS_REGION", raising=False)

    settings = Settings.from_env()

    assert settings.project_name == "Real-Time Energy Forecasting and Anomaly Detection"
    assert settings.environment == "dev"
    assert settings.aws_region == "eu-west-2"
