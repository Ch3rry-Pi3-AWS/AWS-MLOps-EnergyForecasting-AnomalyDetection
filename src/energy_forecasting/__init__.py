"""Core package for the AWS energy forecasting and anomaly-detection project.

The package groups together lightweight helpers for configuration, ingestion,
transformation, orchestration, and machine-learning scaffolding so the
repository can evolve beyond infrastructure-only work into a production-style
Python codebase.

Examples
--------
Import the shared settings helper:

>>> from energy_forecasting.config.settings import Settings
>>> isinstance(Settings.from_env().environment, str)
True
"""
