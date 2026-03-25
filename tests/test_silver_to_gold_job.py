"""Tests for local helper functions in the Silver-to-Gold Glue job script.

Examples
--------
Run just this test module locally:

>>> # pytest tests/test_silver_to_gold_job.py
"""

from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_glue_job_module():
    """
    Import the Glue job module directly from its file path for local tests.

    Returns
    -------
    module
        Imported `silver_to_gold.py` module object.
    """

    module_path = Path(__file__).resolve().parent.parent / "glue" / "jobs" / "silver_to_gold.py"
    spec = importlib.util.spec_from_file_location("glue_silver_to_gold_job", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_normalise_prefix_removes_outer_slashes():
    """Check that Gold prefixes are normalised before URI construction."""

    module = _load_glue_job_module()

    result = module.normalise_prefix("/gold/forecast_features/")

    assert result == "gold/forecast_features"


def test_build_s3_uri_appends_trailing_slash():
    """Check that generated Gold dataset URIs keep the expected trailing slash."""

    module = _load_glue_job_module()

    result = module.build_s3_uri("dl-energyops-dev-creative-antelope", "gold/anomaly_features")

    assert result == "s3://dl-energyops-dev-creative-antelope/gold/anomaly_features/"


def test_job_argument_names_include_required_silver_and_gold_inputs():
    """Check that the job exposes the Silver input and Gold output arguments it needs."""

    module = _load_glue_job_module()

    assert "SILVER_ENERGY_PREFIX" in module.JOB_ARGUMENT_NAMES
    assert "SILVER_WEATHER_PREFIX" in module.JOB_ARGUMENT_NAMES
    assert "GOLD_FORECAST_FEATURES_PREFIX" in module.JOB_ARGUMENT_NAMES
    assert "GOLD_ANOMALY_FEATURES_PREFIX" in module.JOB_ARGUMENT_NAMES
