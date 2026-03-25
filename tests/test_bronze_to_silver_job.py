"""Tests for local helper functions in the Bronze-to-Silver Glue job script.

Examples
--------
Run just this test module locally:

>>> # pytest tests/test_bronze_to_silver_job.py
"""

from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_glue_job_module():
    """Import the Glue job module directly from its file path for local tests."""

    module_path = Path(__file__).resolve().parent.parent / "glue" / "jobs" / "bronze_to_silver.py"
    spec = importlib.util.spec_from_file_location("glue_bronze_to_silver_job", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_normalise_prefix_removes_outer_slashes():
    """Check that S3 prefixes are normalised before URI construction."""

    module = _load_glue_job_module()

    result = module.normalise_prefix("/silver/weather/")

    assert result == "silver/weather"


def test_build_s3_uri_appends_trailing_slash():
    """Check that generated S3 URIs keep the trailing slash Glue expects."""

    module = _load_glue_job_module()

    result = module.build_s3_uri("dl-energyops-dev-creative-antelope", "silver/energy")

    assert result == "s3://dl-energyops-dev-creative-antelope/silver/energy/"


def test_job_argument_names_include_required_catalogue_inputs():
    """Check that the job exposes the catalogue arguments it depends on."""

    module = _load_glue_job_module()

    assert "BRONZE_DATABASE_NAME" in module.JOB_ARGUMENT_NAMES
    assert "ENERGY_TABLE_NAME" in module.JOB_ARGUMENT_NAMES
    assert "WEATHER_TABLE_NAME" in module.JOB_ARGUMENT_NAMES
