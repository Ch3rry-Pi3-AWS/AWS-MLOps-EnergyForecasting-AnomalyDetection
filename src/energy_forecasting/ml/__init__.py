"""Machine-learning helpers for training and deployment scaffolding.

Examples
--------
>>> from energy_forecasting.ml.pipeline import (
...     build_model_package_group_name,
...     build_training_job_name,
... )
>>> build_training_job_name("energyops-dev-creative-antelope", "forecast-xgb")
'energyops-dev-creative-antelope-forecast-xgb-train'
>>> build_model_package_group_name("energyops-dev-creative-antelope", "forecast")
'energyops-dev-creative-antelope-forecast-registry'
"""
