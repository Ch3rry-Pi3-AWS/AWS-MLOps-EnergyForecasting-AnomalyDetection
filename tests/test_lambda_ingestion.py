"""Tests for the lightweight ingestion Lambda helper functions.

Examples
--------
Run just this test module locally:

>>> # pytest tests/test_lambda_ingestion.py
"""

from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_lambda_module():
    """Import the Lambda module directly from its file path for local tests."""

    module_path = Path(__file__).resolve().parent.parent / "lambda" / "ingestion" / "app.py"
    spec = importlib.util.spec_from_file_location("lambda_ingestion_app", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_join_url_normalises_slashes():
    """Check that URL joining does not duplicate path separators."""

    module = _load_lambda_module()

    result = module._join_url("https://data.elexon.co.uk/", "/bmrs/api/v1/datasets/ITSDO")

    assert result == "https://data.elexon.co.uk/bmrs/api/v1/datasets/ITSDO"


def test_build_partitioned_s3_key_uses_source_and_date():
    """Check that Bronze object keys preserve source name and ingestion date."""

    module = _load_lambda_module()

    result = module._build_partitioned_s3_key(
        prefix="bronze/raw",
        source_name="energy",
        request_id="request-123",
        event_time_utc="2026-03-24T22:30:00+00:00",
    )

    assert result == "bronze/raw/energy/dt=2026-03-24/request-123.json"


def test_build_source_record_counts_elexon_rows():
    """Check that energy source records capture the Elexon row count."""

    module = _load_lambda_module()

    result = module._build_source_record(
        source_name="energy",
        key="bronze/raw/energy/dt=2026-03-24/request-123.json",
        payload={"data": [{"demand": 1}, {"demand": 2}]},
    )

    assert result == {
        "source_name": "energy",
        "s3_key": "bronze/raw/energy/dt=2026-03-24/request-123.json",
        "record_count": 2,
    }


def test_build_source_record_summarises_weather_horizon():
    """Check that weather source records summarise the returned forecast horizon."""

    module = _load_lambda_module()

    result = module._build_source_record(
        source_name="weather",
        key="bronze/raw/weather/dt=2026-03-24/request-123.json",
        payload={
            "hourly": {
                "time": [
                    "2026-03-24T00:00",
                    "2026-03-24T01:00",
                    "2026-03-24T02:00",
                ]
            }
        },
    )

    assert result == {
        "source_name": "weather",
        "s3_key": "bronze/raw/weather/dt=2026-03-24/request-123.json",
        "hourly_timestamp_count": 3,
        "forecast_start_time": "2026-03-24T00:00",
        "forecast_end_time": "2026-03-24T02:00",
    }
