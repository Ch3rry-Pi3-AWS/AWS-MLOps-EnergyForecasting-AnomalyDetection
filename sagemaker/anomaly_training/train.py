"""Train a first anomaly model from Gold anomaly features.

This entry point runs inside a SageMaker scikit-learn training container. It
loads the Parquet files from the Gold anomaly-features channel, fits a simple
unsupervised anomaly detector, and persists both the trained model bundle and
basic bootstrap metrics for later registration.

Notes
-----
- The goal here is to establish an end-to-end anomaly-detection training and
  registration path, not to claim a final production-grade detector.
- The baseline model is `IsolationForest`, which works well enough for a first
  unsupervised tabular anomaly workflow.
- Very small early-stage datasets are padded by repeating rows so the
  SageMaker pipeline can still validate the MLOps plumbing before the
  scheduled ingestion jobs have accumulated much history.

Examples
--------
This script is executed by SageMaker rather than directly from the host shell:

>>> # SageMaker launches this via the anomaly-training runner.
"""

from __future__ import annotations

import json
import math
import os
from pathlib import Path

import joblib
import pandas as pd
from sklearn.ensemble import IsolationForest


def list_parquet_files(root: Path) -> list[Path]:
    """Recursively collect Parquet files from a SageMaker input channel."""

    return sorted(path for path in root.rglob("*.parquet") if path.is_file())


def load_training_frame(root: Path) -> pd.DataFrame:
    """
    Load every Parquet fragment from the Gold anomaly-features channel.

    Parameters
    ----------
    root : Path
        Root directory of the SageMaker training input channel.

    Returns
    -------
    pandas.DataFrame
        Concatenated anomaly-feature frame.
    """

    parquet_files = list_parquet_files(root)
    if not parquet_files:
        raise FileNotFoundError(f"No Parquet files were found under anomaly training input: {root}")

    frames = [pd.read_parquet(path) for path in parquet_files]
    return pd.concat(frames, ignore_index=True)


def build_feature_frame(frame: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """
    Derive numeric anomaly-detection features from the Gold anomaly dataset.

    Parameters
    ----------
    frame : pandas.DataFrame
        Raw Gold anomaly-features frame.

    Returns
    -------
    tuple[pandas.DataFrame, list[str]]
        Numeric feature matrix and selected feature names.
    """

    working = frame.copy()
    if "interval_start_utc" in working.columns:
        working = working.sort_values("interval_start_utc").reset_index(drop=True)

    candidate_columns = [
        column
        for column in working.columns
        if column not in {"interval_start_utc", "settlement_date", "dataset_name"}
    ]

    numeric_columns = [
        column for column in candidate_columns if pd.api.types.is_numeric_dtype(working[column])
    ]
    if not numeric_columns:
        raise ValueError("No numeric feature columns were available for anomaly training.")

    feature_frame = working[numeric_columns].fillna(0.0)
    return feature_frame, numeric_columns


def expand_bootstrap_frame(features: pd.DataFrame, minimum_rows: int = 8) -> pd.DataFrame:
    """
    Repeat tiny bootstrap datasets so the anomaly detector can still fit.

    Parameters
    ----------
    features : pandas.DataFrame
        Numeric feature matrix prepared for training.
    minimum_rows : int, default=8
        Minimum row count used for the bootstrap training baseline.

    Returns
    -------
    pandas.DataFrame
        Expanded feature frame when the original dataset is too small.
    """

    if len(features) >= minimum_rows:
        return features

    if features.empty:
        raise ValueError("At least one anomaly-feature row is required to train the anomaly baseline.")

    repeat_factor = math.ceil(minimum_rows / len(features))
    expanded = pd.concat([features] * repeat_factor, ignore_index=True)
    return expanded.iloc[:minimum_rows].copy()


def build_estimator() -> IsolationForest:
    """
    Create the first unsupervised anomaly baseline.

    Returns
    -------
    sklearn.ensemble.IsolationForest
        Configured anomaly detector.
    """

    return IsolationForest(
        n_estimators=200,
        contamination=0.05,
        random_state=42,
    )


def main() -> None:
    """Train the baseline anomaly detector and write model plus metrics artefacts."""

    train_channel = Path(os.environ.get("SM_CHANNEL_TRAIN", "/opt/ml/input/data/train"))
    model_dir = Path(os.environ.get("SM_MODEL_DIR", "/opt/ml/model"))
    output_dir = Path(os.environ.get("SM_OUTPUT_DATA_DIR", "/opt/ml/output/data"))

    model_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    frame = load_training_frame(train_channel)
    features, feature_names = build_feature_frame(frame)
    expanded_features = expand_bootstrap_frame(features)

    model = build_estimator()
    model.fit(expanded_features)

    # Compute anomaly scores on the original, non-expanded frame so the saved
    # threshold reflects the real dataset rather than the bootstrap repeats.
    anomaly_scores = model.score_samples(features)
    threshold = float(pd.Series(anomaly_scores).quantile(0.05))
    predicted_flags = anomaly_scores < threshold

    metrics = {
        "score_mean": float(pd.Series(anomaly_scores).mean()),
        "score_std": float(pd.Series(anomaly_scores).std(ddof=0)),
        "score_threshold": threshold,
        "training_rows": int(len(features)),
        "bootstrap_training_rows": int(len(expanded_features)),
        "detected_anomaly_rows": int(predicted_flags.sum()),
        "feature_columns": feature_names,
    }

    joblib.dump(
        {
            "model": model,
            "feature_columns": feature_names,
            "score_threshold": threshold,
        },
        model_dir / "model.joblib",
    )
    (output_dir / "evaluation.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
