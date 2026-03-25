"""Machine-learning helpers for training and deployment scaffolding.

Examples
--------
>>> from energy_forecasting.ml.pipeline import (
...     build_model_package_group_name,
...     build_timestamped_sagemaker_name,
...     build_training_job_name,
...     build_timestamped_training_job_name,
... )
>>> build_training_job_name("energyops-dev-creative-antelope", "forecast-xgb")
'energyops-dev-creative-antelope-forecast-xgb-train'
>>> build_timestamped_sagemaker_name(
...     "energyops-dev-creative-antelope-forecast-endpoint-config",
...     "20260325160000",
... )
'energyops-dev-creative-antelope-forecast-endpoin-20260325160000'
>>> build_model_package_group_name("energyops-dev-creative-antelope", "forecast")
'energyops-dev-creative-antelope-forecast-registry'
>>> build_timestamped_training_job_name(
...     "energyops-dev-creative-antelope-forecast-sklearn-train",
...     "20260325113000",
... )
'energyops-dev-creative-antelope-forecast-sklearn-train-20260325113000'
"""
