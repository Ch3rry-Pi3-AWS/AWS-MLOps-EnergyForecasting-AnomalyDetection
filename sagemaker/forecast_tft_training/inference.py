"""Inference entry point for the Temporal Fusion Transformer forecast model.

The payload should provide a chronological sequence of rows containing the
encoder history followed by the forecast horizon rows. For meaningful
forecasts, the encoder rows should include observed `demand_mw` values while
the decoder rows provide the known future covariates such as calendar and
weather features.

Examples
--------
The SageMaker hosting container calls these hook functions automatically:

>>> # model_fn("/opt/ml/model")  # doctest: +SKIP
"""

from __future__ import annotations

import json
import pickle
from pathlib import Path
from typing import Any

import pandas as pd
from pytorch_forecasting import TemporalFusionTransformer, TimeSeriesDataSet


def model_fn(model_dir: str) -> dict[str, Any]:
    """Load the persisted TFT checkpoint and dataset metadata from SageMaker storage."""

    model_root = Path(model_dir)
    metadata = json.loads((model_root / "metadata.json").read_text(encoding="utf-8"))
    with (model_root / "dataset_parameters.pkl").open("rb") as handle:
        dataset_parameters = pickle.load(handle)
    model = TemporalFusionTransformer.load_from_checkpoint(str(model_root / "model.ckpt"))
    return {
        "model": model,
        "metadata": metadata,
        "dataset_parameters": dataset_parameters,
    }


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
        raise ValueError("Inference payload must be a list of chronological feature records.")
    return pd.DataFrame(payload)


def prepare_inference_frame(input_data: pd.DataFrame, metadata: dict[str, Any]) -> pd.DataFrame:
    """Prepare a chronological TFT inference frame from raw request rows."""

    context_length = int(metadata["context_length"])
    prediction_length = int(metadata["prediction_length"])
    required_rows = context_length + prediction_length
    if len(input_data) < required_rows:
        raise ValueError(
            "TFT inference requires at least "
            f"{required_rows} chronological rows covering encoder history plus forecast horizon."
        )

    frame = input_data.copy()
    if "interval_start_utc" in frame.columns:
        frame["interval_start_utc"] = pd.to_datetime(frame["interval_start_utc"], utc=True, errors="coerce")
        frame = frame.sort_values("interval_start_utc").reset_index(drop=True)
    else:
        frame = frame.reset_index(drop=True)

    feature_columns = metadata.get("feature_columns", [])
    for column in feature_columns:
        frame[column] = pd.to_numeric(frame.get(column, 0.0), errors="coerce").fillna(0.0)

    decoder_start = len(frame) - prediction_length
    if "demand_mw" in frame.columns:
        demand = pd.to_numeric(frame["demand_mw"], errors="coerce")
    else:
        demand = pd.Series([0.0] * len(frame), dtype="float64")
    demand.iloc[:decoder_start] = demand.iloc[:decoder_start].fillna(0.0)
    frame["demand_mw"] = demand
    frame["series_id"] = metadata.get("series_id", "gb_demand")
    frame["time_idx"] = range(len(frame))
    return frame[["series_id", "time_idx", "demand_mw", *feature_columns]].copy()


def predict_fn(input_data: pd.DataFrame, model_bundle: dict[str, Any]) -> list[float]:
    """Run TFT inference over the supplied encoder-history and forecast-horizon rows."""

    metadata = model_bundle["metadata"]
    dataset_parameters = model_bundle["dataset_parameters"]
    frame = prepare_inference_frame(input_data, metadata)
    dataset = TimeSeriesDataSet.from_parameters(
        dataset_parameters,
        frame,
        predict=True,
        stop_randomization=True,
    )
    dataloader = dataset.to_dataloader(train=False, batch_size=1, num_workers=0)
    predictions = model_bundle["model"].predict(dataloader, mode="prediction")
    if hasattr(predictions, "detach"):
        return [float(value) for value in predictions.detach().cpu().reshape(-1).tolist()]
    return [float(value) for value in predictions.reshape(-1).tolist()]


def output_fn(prediction: list[float], accept: str) -> tuple[str, str]:
    """Serialise model predictions back to JSON."""

    if accept not in {"application/json", "*/*"}:
        raise ValueError(f"Unsupported accept type: {accept}")
    return json.dumps({"predictions": prediction}), "application/json"
