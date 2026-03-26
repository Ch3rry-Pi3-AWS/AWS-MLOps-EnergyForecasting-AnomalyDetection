"""Train a One-Class SVM anomaly model from Gold anomaly features.

Examples
--------
This script is executed by SageMaker rather than directly from the host shell:

>>> # SageMaker launches this via the anomaly One-Class SVM runner.
"""

from __future__ import annotations

import json
import math
import os
from pathlib import Path

import joblib
import pandas as pd
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import OneClassSVM

EXCLUDED_COLUMNS = {
    "interval_start_utc",
    "interval_end_utc",
    "settlement_date",
    "dataset_name",
    "publish_time_utc",
    "bronze_ingestion_date",
}


def list_parquet_files(root: Path) -> list[Path]:
    """Recursively collect Parquet files from a SageMaker input channel."""

    return sorted(path for path in root.rglob("*.parquet") if path.is_file())


def load_training_frame(root: Path) -> pd.DataFrame:
    """Load every Parquet fragment from the Gold anomaly-features channel."""

    parquet_files = list_parquet_files(root)
    if not parquet_files:
        raise FileNotFoundError(f"No Parquet files were found under anomaly One-Class SVM training input: {root}")

    frames = [pd.read_parquet(path) for path in parquet_files]
    return pd.concat(frames, ignore_index=True)


def build_feature_frame(frame: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """Derive numeric anomaly-detection features from the Gold anomaly dataset."""

    working = frame.copy()
    if "interval_start_utc" in working.columns:
        working = working.sort_values("interval_start_utc").reset_index(drop=True)

    candidate_columns = [
        column for column in working.columns if column not in EXCLUDED_COLUMNS
    ]
    numeric_columns = [
        column for column in candidate_columns if pd.api.types.is_numeric_dtype(working[column])
    ]
    if not numeric_columns:
        raise ValueError("No numeric feature columns were available for anomaly One-Class SVM training.")

    feature_frame = working[numeric_columns].fillna(0.0)
    return feature_frame, numeric_columns


def expand_bootstrap_frame(features: pd.DataFrame, minimum_rows: int = 16) -> pd.DataFrame:
    """Repeat tiny bootstrap datasets so the One-Class SVM can still fit."""

    if len(features) >= minimum_rows:
        return features

    if features.empty:
        raise ValueError("At least one anomaly-feature row is required to train the One-Class SVM baseline.")

    repeat_factor = math.ceil(minimum_rows / len(features))
    expanded = pd.concat([features] * repeat_factor, ignore_index=True)
    return expanded.iloc[:minimum_rows].copy()


def build_estimator() -> Pipeline:
    """Create the One-Class SVM anomaly baseline."""

    return Pipeline(
        steps=[
            ("scaler", StandardScaler()),
            ("ocsvm", OneClassSVM(kernel="rbf", gamma="scale", nu=0.05)),
        ]
    )


def main() -> None:
    """Train the One-Class SVM anomaly detector and write model plus metrics artefacts."""

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

    anomaly_scores = -model.decision_function(features)
    score_series = pd.Series(anomaly_scores, dtype="float64")
    score_threshold = float(score_series.quantile(0.95))
    predicted_flags = score_series > score_threshold

    metrics = {
        "score_mean": float(score_series.mean()),
        "score_std": float(score_series.std(ddof=0)),
        "score_threshold": score_threshold,
        "training_rows": int(len(features)),
        "bootstrap_training_rows": int(len(expanded_features)),
        "detected_anomaly_rows": int(predicted_flags.sum()),
        "feature_columns": feature_names,
        "anomaly_algorithm": "one_class_svm",
    }

    joblib.dump(
        {
            "model": model,
            "feature_columns": feature_names,
            "score_threshold": score_threshold,
        },
        model_dir / "model.joblib",
    )
    (output_dir / "evaluation.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
