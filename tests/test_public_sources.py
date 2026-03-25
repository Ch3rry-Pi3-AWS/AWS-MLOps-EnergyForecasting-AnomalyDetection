"""Tests for the default public source catalogue.

Examples
--------
Run just this test module locally:

>>> # pytest tests/test_public_sources.py
"""

from energy_forecasting.ingestion.public_sources import default_sources


def test_default_sources_include_energy_and_weather():
    """Ensure the initial source list includes both energy and weather feeds."""

    names = [source.name for source in default_sources()]

    assert "elexon-bmrs" in names
    assert "open-meteo" in names
