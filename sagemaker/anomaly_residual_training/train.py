"""Train a residual-based anomaly model from Gold anomaly features.

This entry point runs inside a SageMaker scikit-learn container. It fits a
regression model to predict demand, then scores anomalies from the standardized
absolute residual relative to the rolling demand volatility already present in
the Gold anomaly dataset.

Examples
--------
This script is executed by SageMaker rather than directly from the host shell:

>>> # SageMaker launches this via the anomaly residual-training runner.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import joblib
import pandas as pd
from sklearn.dummy import DummyRegressor
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

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
        raise FileNotFoundError(f"No Parquet files were found under anomaly residual training input: {root}")

    frames = [pd.read_parquet(path) for path in parquet_files]
    return pd.concat(frames, ignore_index=True)


def build_feature_frame(frame: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series, list[str]]:
    """Derive numeric regression features and the demand target from the Gold anomaly dataset."""

    if "demand_mw" not in frame.columns:
        raise KeyError("Gold anomaly-features frame must contain a 'demand_mw' target column.")

    working = frame.dropna(subset=["demand_mw"]).copy()
    if "interval_start_utc" in working.columns:
        working = working.sort_values("interval_start_utc").reset_index(drop=True)

    candidate_columns = [
        column for column in working.columns if column not in EXCLUDED_COLUMNS | {"demand_mw"}
    ]
    numeric_columns = [
        column for column in candidate_columns if pd.api.types.is_numeric_dtype(working[column])
    ]
    if not numeric_columns:
        raise ValueError("No numeric feature columns were available for anomaly residual training.")

    feature_frame = working[numeric_columns].fillna(0.0)
    target = working["demand_mw"].astype(float)
    return feature_frame, target, numeric_columns


def split_train_test(
    features: pd.DataFrame,
    target: pd.Series,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.Series, pd.Series]:
    """Perform a chronological train-test split for residual scoring."""

    row_count = len(target)
    if row_count < 3:
        raise ValueError("At least three anomaly-feature rows are required to train the residual baseline.")

    split_index = row_count - 1 if row_count < 10 else max(int(row_count * 0.8), 1)
    return (
        features.iloc[:split_index],
        features.iloc[split_index:],
        target.iloc[:split_index],
        target.iloc[split_index:],
    )


def build_estimator(training_rows: int):
    """Create the residual baseline regressor, falling back on tiny datasets."""

    if training_rows < 32:
        return DummyRegressor(strategy="mean")
    return GradientBoostingRegressor(random_state=42)


def calculate_r2(y_true: pd.Series, y_pred: pd.Series) -> float:
    """Compute a safe `R^2` value for chronological holdout evaluation."""

    if len(y_true) < 2:
        return 0.0
    return float(r2_score(y_true, y_pred))


def calculate_residual_scores(
    frame: pd.DataFrame,
    *,
    actual: pd.Series,
    predicted: pd.Series,
) -> pd.Series:
    """Convert forecast residuals into standardized anomaly scores."""

    volatility = pd.to_numeric(frame.get("rolling_stddev_48_demand_mw"), errors="coerce").fillna(0.0)
    fallback_scale = max(float(actual.std(ddof=0)), 1.0)
    safe_scale = volatility.where(volatility > 0, fallback_scale)
    standardized = (actual - predicted).abs() / safe_scale
    return standardized.astype(float)


def main() -> None:
    """Train the residual-scoring anomaly model and write model plus metrics artefacts."""

    train_channel = Path(os.environ.get("SM_CHANNEL_TRAIN", "/opt/ml/input/data/train"))
    model_dir = Path(os.environ.get("SM_MODEL_DIR", "/opt/ml/model"))
    output_dir = Path(os.environ.get("SM_OUTPUT_DATA_DIR", "/opt/ml/output/data"))

    model_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    frame = load_training_frame(train_channel)
    features, target, feature_names = build_feature_frame(frame)
    x_train, x_test, y_train, y_test = split_train_test(features, target)

    model = build_estimator(len(y_train))
    model.fit(x_train, y_train)

    full_predictions = pd.Series(model.predict(features), index=features.index, dtype="float64")
    holdout_predictions = pd.Series(model.predict(x_test), index=x_test.index, dtype="float64")
    residual_scores = calculate_residual_scores(frame, actual=target, predicted=full_predictions)
    score_threshold = float(residual_scores.quantile(0.95))
    predicted_flags = residual_scores > score_threshold

    metrics = {
        "mae": float(mean_absolute_error(y_test, holdout_predictions)),
        "rmse": float(mean_squared_error(y_test, holdout_predictions, squared=False)),
        "r2": calculate_r2(y_test, holdout_predictions),
        "score_threshold": score_threshold,
        "score_mean": float(residual_scores.mean()),
        "score_std": float(residual_scores.std(ddof=0)),
        "training_rows": int(len(features)),
        "bootstrap_training_rows": int(len(y_train)),
        "detected_anomaly_rows": int(predicted_flags.sum()),
        "feature_columns": feature_names,
        "anomaly_algorithm": "residual_scoring",
        "regression_algorithm": type(model).__name__,
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
