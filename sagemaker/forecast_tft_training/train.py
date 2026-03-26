"""Train a Temporal Fusion Transformer forecast model from Gold forecast features.

This entry point runs inside a SageMaker PyTorch training container. It loads
the Parquet files placed under the training channel, builds a single-series
time-indexed dataset for GB demand, trains a Temporal Fusion Transformer, and
persists both the fitted checkpoint and holdout evaluation metrics.

Examples
--------
This script is executed by SageMaker rather than directly from the host shell:

>>> # SageMaker launches this via the TFT forecast-training runner.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import pickle
import shutil
from pathlib import Path
from typing import Any

import pandas as pd
import torch
from lightning.pytorch import Trainer, seed_everything
from lightning.pytorch.callbacks import EarlyStopping, ModelCheckpoint
from pytorch_forecasting import TemporalFusionTransformer, TimeSeriesDataSet
from pytorch_forecasting.data import GroupNormalizer
from pytorch_forecasting.metrics import QuantileLoss

PREFERRED_KNOWN_REAL_COLUMNS = [
    "settlement_period",
    "temperature_2m",
    "relative_humidity_2m",
    "wind_speed_10m",
    "interval_hour",
    "day_of_week",
    "month_of_year",
    "is_weekend",
]


def parse_args() -> argparse.Namespace:
    """Parse SageMaker-supplied hyperparameters."""

    parser = argparse.ArgumentParser(description="Train a TFT forecast model from Gold forecast features.")
    parser.add_argument("--context_length", type=int, default=48)
    parser.add_argument("--prediction_length", type=int, default=48)
    parser.add_argument("--max_epochs", type=int, default=30)
    parser.add_argument("--batch_size", type=int, default=64)
    parser.add_argument("--hidden_size", type=int, default=32)
    parser.add_argument("--attention_head_size", type=int, default=4)
    parser.add_argument("--hidden_continuous_size", type=int, default=16)
    parser.add_argument("--dropout", type=float, default=0.1)
    parser.add_argument("--learning_rate", type=float, default=0.03)
    return parser.parse_args()


def list_parquet_files(root: Path) -> list[Path]:
    """Recursively collect Parquet files from a SageMaker input channel."""

    return sorted(path for path in root.rglob("*.parquet") if path.is_file())


def load_training_frame(root: Path) -> pd.DataFrame:
    """Load and concatenate all Parquet fragments from the Gold forecast channel."""

    parquet_files = list_parquet_files(root)
    if not parquet_files:
        raise FileNotFoundError(f"No Parquet files were found under TFT training input: {root}")

    frames = [pd.read_parquet(path) for path in parquet_files]
    return pd.concat(frames, ignore_index=True)


def build_training_frame(frame: pd.DataFrame) -> tuple[pd.DataFrame, list[str], list[str]]:
    """Prepare a chronological TFT training frame and detect constant known features."""

    if "demand_mw" not in frame.columns:
        raise KeyError("Gold forecast-features frame must contain a 'demand_mw' target column.")

    working = frame.dropna(subset=["demand_mw"]).copy()
    if "interval_start_utc" in working.columns:
        working["interval_start_utc"] = pd.to_datetime(working["interval_start_utc"], utc=True, errors="coerce")
        working = working.sort_values("interval_start_utc").reset_index(drop=True)

    candidate_columns = [
        column
        for column in PREFERRED_KNOWN_REAL_COLUMNS
        if column in working.columns and pd.api.types.is_numeric_dtype(working[column])
    ]
    retained_columns = [
        column for column in candidate_columns if working[column].nunique(dropna=False) > 1
    ]
    dropped_columns = [column for column in candidate_columns if column not in retained_columns]

    for column in retained_columns:
        working[column] = pd.to_numeric(working[column], errors="coerce").fillna(0.0)

    working["demand_mw"] = pd.to_numeric(working["demand_mw"], errors="coerce")
    working = working.dropna(subset=["demand_mw"]).reset_index(drop=True)
    working["series_id"] = "gb_demand"
    working["time_idx"] = range(len(working))

    columns = ["series_id", "time_idx", "demand_mw", *retained_columns]
    return working[columns].copy(), retained_columns, dropped_columns


def validate_row_count(frame: pd.DataFrame, *, context_length: int, prediction_length: int) -> None:
    """Ensure there is enough chronological history to train and evaluate TFT."""

    minimum_rows = context_length + prediction_length + 1
    if len(frame) < minimum_rows:
        raise ValueError(
            "Not enough forecast rows were available for TFT training. "
            f"Need at least {minimum_rows} rows but only found {len(frame)}."
        )


def build_datasets(
    frame: pd.DataFrame,
    *,
    known_feature_columns: list[str],
    context_length: int,
    prediction_length: int,
) -> tuple[TimeSeriesDataSet, TimeSeriesDataSet]:
    """Build the TFT training and validation datasets from a single time series."""

    training_cutoff = int(frame["time_idx"].max() - prediction_length)
    training = TimeSeriesDataSet(
        frame[lambda df: df.time_idx <= training_cutoff],
        time_idx="time_idx",
        target="demand_mw",
        group_ids=["series_id"],
        min_encoder_length=context_length,
        max_encoder_length=context_length,
        min_prediction_length=prediction_length,
        max_prediction_length=prediction_length,
        static_categoricals=["series_id"],
        time_varying_known_reals=known_feature_columns,
        time_varying_unknown_reals=["demand_mw"],
        target_normalizer=GroupNormalizer(groups=["series_id"]),
        add_relative_time_idx=True,
        add_target_scales=True,
        add_encoder_length=True,
    )
    validation = TimeSeriesDataSet.from_dataset(
        training,
        frame,
        predict=True,
        stop_randomization=True,
    )
    return training, validation


def flatten_prediction_values(predictions: Any) -> list[float]:
    """Flatten model predictions into a simple list of floats."""

    if hasattr(predictions, "detach"):
        return [float(value) for value in predictions.detach().cpu().reshape(-1).tolist()]
    if hasattr(predictions, "reshape"):
        return [float(value) for value in predictions.reshape(-1).tolist()]
    if isinstance(predictions, list):
        flattened: list[float] = []
        for item in predictions:
            flattened.extend(flatten_prediction_values(item))
        return flattened
    return [float(predictions)]


def calculate_mae(actual: list[float], predicted: list[float]) -> float:
    """Calculate mean absolute error without external metric dependencies."""

    return float(sum(abs(a - p) for a, p in zip(actual, predicted)) / len(actual))


def calculate_rmse(actual: list[float], predicted: list[float]) -> float:
    """Calculate root mean squared error without external metric dependencies."""

    return float(math.sqrt(sum((a - p) ** 2 for a, p in zip(actual, predicted)) / len(actual)))


def calculate_r2(actual: list[float], predicted: list[float]) -> float:
    """Calculate a safe `R^2` score for a holdout horizon."""

    if len(actual) < 2:
        return 0.0
    mean_actual = sum(actual) / len(actual)
    total_sum_squares = sum((value - mean_actual) ** 2 for value in actual)
    if total_sum_squares == 0:
        return 0.0
    residual_sum_squares = sum((a - p) ** 2 for a, p in zip(actual, predicted))
    return float(1.0 - (residual_sum_squares / total_sum_squares))


def save_model_bundle(
    *,
    model_dir: Path,
    best_checkpoint_path: Path,
    dataset_parameters: dict[str, Any],
    metadata: dict[str, Any],
) -> None:
    """Persist the TFT checkpoint and supporting metadata for inference."""

    shutil.copy2(best_checkpoint_path, model_dir / "model.ckpt")
    with (model_dir / "dataset_parameters.pkl").open("wb") as handle:
        pickle.dump(dataset_parameters, handle)
    (model_dir / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")


def main() -> None:
    """Train the TFT model and write model plus evaluation artefacts."""

    args = parse_args()
    train_channel = Path(os.environ.get("SM_CHANNEL_TRAIN", "/opt/ml/input/data/train"))
    model_dir = Path(os.environ.get("SM_MODEL_DIR", "/opt/ml/model"))
    output_dir = Path(os.environ.get("SM_OUTPUT_DATA_DIR", "/opt/ml/output/data"))

    model_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    seed_everything(42, workers=True)
    torch.set_float32_matmul_precision("medium")

    raw_frame = load_training_frame(train_channel)
    training_frame, known_feature_columns, dropped_columns = build_training_frame(raw_frame)
    validate_row_count(
        training_frame,
        context_length=args.context_length,
        prediction_length=args.prediction_length,
    )
    training, validation = build_datasets(
        training_frame,
        known_feature_columns=known_feature_columns,
        context_length=args.context_length,
        prediction_length=args.prediction_length,
    )

    train_dataloader = training.to_dataloader(
        train=True,
        batch_size=args.batch_size,
        num_workers=0,
    )
    val_dataloader = validation.to_dataloader(
        train=False,
        batch_size=args.batch_size,
        num_workers=0,
    )

    checkpoint_callback = ModelCheckpoint(monitor="val_loss", mode="min", save_top_k=1)
    early_stopping = EarlyStopping(monitor="val_loss", mode="min", patience=5, min_delta=1e-4)
    trainer = Trainer(
        accelerator="cpu",
        devices=1,
        max_epochs=args.max_epochs,
        gradient_clip_val=0.1,
        logger=False,
        enable_progress_bar=False,
        enable_model_summary=False,
        callbacks=[checkpoint_callback, early_stopping],
    )

    tft = TemporalFusionTransformer.from_dataset(
        training,
        learning_rate=args.learning_rate,
        hidden_size=args.hidden_size,
        attention_head_size=args.attention_head_size,
        dropout=args.dropout,
        hidden_continuous_size=args.hidden_continuous_size,
        loss=QuantileLoss(),
        log_interval=-1,
        reduce_on_plateau_patience=4,
    )
    trainer.fit(tft, train_dataloaders=train_dataloader, val_dataloaders=val_dataloader)

    best_checkpoint_path = Path(checkpoint_callback.best_model_path or "")
    if not best_checkpoint_path.exists():
        raise FileNotFoundError("TFT training finished without producing a best-model checkpoint.")

    best_model = TemporalFusionTransformer.load_from_checkpoint(str(best_checkpoint_path))
    predictions = flatten_prediction_values(best_model.predict(val_dataloader, mode="prediction"))
    actual = training_frame["demand_mw"].tail(args.prediction_length).astype(float).tolist()
    predictions = predictions[: len(actual)]

    metrics = {
        "mae": calculate_mae(actual, predictions),
        "rmse": calculate_rmse(actual, predictions),
        "r2": calculate_r2(actual, predictions),
        "training_rows": int(len(training_frame) - args.prediction_length),
        "test_rows": int(args.prediction_length),
        "feature_columns": known_feature_columns,
        "dropped_constant_feature_columns": dropped_columns,
        "context_length": int(args.context_length),
        "prediction_length": int(args.prediction_length),
        "hidden_size": int(args.hidden_size),
        "attention_head_size": int(args.attention_head_size),
        "hidden_continuous_size": int(args.hidden_continuous_size),
        "dropout": float(args.dropout),
        "learning_rate": float(args.learning_rate),
        "forecast_algorithm": "tft",
    }

    save_model_bundle(
        model_dir=model_dir,
        best_checkpoint_path=best_checkpoint_path,
        dataset_parameters=training.get_parameters(),
        metadata={
            "feature_columns": known_feature_columns,
            "dropped_constant_feature_columns": dropped_columns,
            "context_length": int(args.context_length),
            "prediction_length": int(args.prediction_length),
            "forecast_algorithm": "tft",
            "series_id": "gb_demand",
        },
    )
    (output_dir / "evaluation.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
