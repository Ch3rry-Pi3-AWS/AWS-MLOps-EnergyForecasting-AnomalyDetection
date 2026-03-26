"""Inference entry point for the One-Class SVM anomaly model package.

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
    """Load the persisted One-Class SVM model bundle from SageMaker model storage."""

    return joblib.load(Path(model_dir) / "model.joblib")


def input_fn(request_body: str, content_type: str) -> pd.DataFrame:
    """
    Parse incoming anomaly-inference payloads into a DataFrame.

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


def predict_fn(input_data: pd.DataFrame, model_bundle: dict[str, Any]) -> list[dict[str, float | bool]]:
    """Run One-Class SVM inference and return both scores and boolean flags."""

    feature_columns = model_bundle["feature_columns"]
    aligned = input_data.reindex(columns=feature_columns, fill_value=0.0)
    scores = -model_bundle["model"].decision_function(aligned)
    threshold = model_bundle["score_threshold"]

    return [
        {
            "anomaly_score": float(score),
            "is_anomaly": bool(score > threshold),
        }
        for score in scores
    ]


def output_fn(prediction: list[dict[str, float | bool]], accept: str) -> tuple[str, str]:
    """Serialise anomaly predictions back to JSON."""

    if accept not in {"application/json", "*/*"}:
        raise ValueError(f"Unsupported accept type: {accept}")
    return json.dumps({"predictions": prediction}), "application/json"
