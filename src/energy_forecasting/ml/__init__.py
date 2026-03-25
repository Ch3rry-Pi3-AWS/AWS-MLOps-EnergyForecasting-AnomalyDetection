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
>>> from energy_forecasting.ml.evaluation import evaluate_forecast_metrics
>>> evaluate_forecast_metrics(
...     {"mae": 1200.0, "rmse": 1800.0, "r2": 0.71, "training_rows": 96},
...     {"min_training_rows": 48, "max_mae": 5000.0, "max_rmse": 7000.0, "min_r2": 0.0},
... )["passed"]
True
"""
