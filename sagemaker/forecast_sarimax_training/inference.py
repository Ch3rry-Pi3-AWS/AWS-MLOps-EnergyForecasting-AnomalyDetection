"""Inference entry point for the SARIMAX forecast model package.

This script is bundled into the registered SageMaker model package so the
SARIMAX forecast model can be deployed later without rewriting inference
logic.

Examples
--------
The SageMaker hosting container calls these hook functions automatically:

>>> # model_fn("/opt/ml/model")  # doctest: +SKIP
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import joblib
import pandas as pd


def model_fn(model_dir: str) -> dict[str, Any]:
    """Load the persisted SARIMAX model bundle from SageMaker model storage."""

    return joblib.load(Path(model_dir) / "model.joblib")


def input_fn(request_body: str, content_type: str) -> pd.DataFrame:
    """
    Parse incoming inference payloads into a DataFrame.

    The payload should be JSON in one of two shapes:

    - `{"instances": [{...}, {...}]}`
    - `[{...}, {...}]`
    """

    if content_type != "application/json":
        raise ValueError(f"Unsupported content type: {content_type}")

    payload = json.loads(request_body)
    if isinstance(payload, dict) and "instances" in payload:
        payload = payload["instances"]
    if not isinstance(payload, list):
        raise ValueError("Inference payload must be a list of feature records.")
    return pd.DataFrame(payload)


def predict_fn(input_data: pd.DataFrame, model_bundle: dict[str, Any]) -> list[float]:
    """Forecast the next steps using the fitted SARIMAX state and supplied exogenous rows."""

    feature_columns = model_bundle["feature_columns"]
    aligned_exog = input_data.reindex(columns=feature_columns, fill_value=0.0) if feature_columns else None
    prediction = model_bundle["model"].forecast(steps=len(input_data), exog=aligned_exog)
    return [float(value) for value in prediction]


def output_fn(prediction: list[float], accept: str) -> tuple[str, str]:
    """Serialise model predictions back to JSON."""

    if accept not in {"application/json", "*/*"}:
        raise ValueError(f"Unsupported accept type: {accept}")
    return json.dumps({"predictions": prediction}), "application/json"
