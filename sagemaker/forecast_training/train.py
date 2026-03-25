"""Train a first forecast model from Gold forecast features.

This entry point runs inside a SageMaker scikit-learn training container. It
loads the Parquet files that SageMaker places under the training channel,
derives a simple supervised-learning dataset, and persists both the trained
model and evaluation metrics for later registration.

Notes
-----
- The goal here is not a production-grade forecasting recipe yet.
- The job intentionally starts with a simple baseline regressor so the project
  can produce a real registered model version before adding more advanced
  feature engineering or backtesting logic.
- The script expects the training channel to contain the Gold
  `forecast_features` dataset produced by the Silver-to-Gold Glue job.

Examples
--------
This script is executed by SageMaker rather than directly from the host shell:

>>> # SageMaker launches this via the forecast-training runner.
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


def list_parquet_files(root: Path) -> list[Path]:
    """Recursively collect Parquet files from a SageMaker input channel."""

    return sorted(path for path in root.rglob("*.parquet") if path.is_file())


def load_training_frame(root: Path) -> pd.DataFrame:
    """
    Load every Parquet fragment from the Gold forecast-features channel.

    Parameters
    ----------
    root : Path
        Root directory of the SageMaker training input channel.

    Returns
    -------
    pandas.DataFrame
        Concatenated forecast-feature frame.
    """

    parquet_files = list_parquet_files(root)
    if not parquet_files:
        raise FileNotFoundError(f"No Parquet files were found under training input: {root}")

    frames = [pd.read_parquet(path) for path in parquet_files]
    return pd.concat(frames, ignore_index=True)


def build_feature_frame(frame: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series, list[str]]:
    """
    Derive numeric model features and target from the Gold feature dataset.

    Parameters
    ----------
    frame : pandas.DataFrame
        Raw Gold forecast-features frame.

    Returns
    -------
    tuple[pandas.DataFrame, pandas.Series, list[str]]
        Numeric feature matrix, target series, and selected feature names.
    """

    if "demand_mw" not in frame.columns:
        raise KeyError("Gold forecast-features frame must contain a 'demand_mw' target column.")

    working = frame.dropna(subset=["demand_mw"]).copy()
    if "interval_start_utc" in working.columns:
        working = working.sort_values("interval_start_utc").reset_index(drop=True)

    candidate_columns = [
        column
        for column in working.columns
        if column not in {"demand_mw", "interval_start_utc", "settlement_date", "dataset_name"}
    ]

    numeric_columns = [
        column for column in candidate_columns if pd.api.types.is_numeric_dtype(working[column])
    ]
    if not numeric_columns:
        raise ValueError("No numeric feature columns were available for forecast training.")

    feature_frame = working[numeric_columns].fillna(0.0)
    target = working["demand_mw"]
    return feature_frame, target, numeric_columns


def split_train_test(features: pd.DataFrame, target: pd.Series) -> tuple[pd.DataFrame, pd.DataFrame, pd.Series, pd.Series]:
    """
    Perform a simple chronological split for an initial forecasting baseline.

    The project is time-series oriented, so the split keeps the final 20% of
    rows as the evaluation window instead of shuffling randomly.
    """

    row_count = len(features)
    if row_count < 2:
        # Early dev runs can legitimately have only one landed demand record.
        # Reusing that single row for both train and evaluation is not a sound
        # modelling strategy, but it is enough to validate the end-to-end
        # SageMaker training and model-registry plumbing.
        return features, features, target, target

    # For very small datasets, force at least one holdout row while keeping as
    # many rows as possible in training. Once the dataset grows, revert to the
    # normal chronological 80/20 split.
    split_index = row_count - 1 if row_count < 10 else max(int(row_count * 0.8), 1)
    x_train = features.iloc[:split_index]
    x_test = features.iloc[split_index:]
    y_train = target.iloc[:split_index]
    y_test = target.iloc[split_index:]
    return x_train, x_test, y_train, y_test


def build_estimator(training_row_count: int):
    """
    Choose a sensible baseline estimator for the available training volume.

    Parameters
    ----------
    training_row_count : int
        Number of rows available in the training split.

    Returns
    -------
    sklearn.base.RegressorMixin
        Regressor ready for fitting.

    Notes
    -----
    The project starts with tiny dev datasets, especially before the ingestion
    schedules have accumulated much history. A `DummyRegressor` keeps the
    training-and-registration path working for those small bootstrap datasets,
    while `GradientBoostingRegressor` remains the default once enough rows are
    available to make the baseline slightly more meaningful.
    """

    if training_row_count < 5:
        return DummyRegressor(strategy="mean")
    return GradientBoostingRegressor(random_state=42)


def main() -> None:
    """Train the baseline model and write model plus metrics artefacts."""

    train_channel = Path(os.environ.get("SM_CHANNEL_TRAIN", "/opt/ml/input/data/train"))
    model_dir = Path(os.environ.get("SM_MODEL_DIR", "/opt/ml/model"))
    output_dir = Path(os.environ.get("SM_OUTPUT_DATA_DIR", "/opt/ml/output/data"))

    model_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    frame = load_training_frame(train_channel)
    features, target, feature_names = build_feature_frame(frame)
    x_train, x_test, y_train, y_test = split_train_test(features, target)

    # Start with a robust tabular baseline so the project can complete an
    # end-to-end registration flow before introducing more complex forecasters.
    # For tiny bootstrap datasets, fall back to a trivial mean predictor so
    # the MLOps plumbing can still be exercised end to end.
    model = build_estimator(len(x_train))
    model.fit(x_train, y_train)

    predictions = model.predict(x_test)
    metrics = {
      "mae": float(mean_absolute_error(y_test, predictions)),
      "rmse": float(mean_squared_error(y_test, predictions, squared=False)),
      "r2": float(r2_score(y_test, predictions)),
      "training_rows": int(len(x_train)),
      "test_rows": int(len(x_test)),
      "feature_columns": feature_names,
    }

    joblib.dump(
        {
            "model": model,
            "feature_columns": feature_names,
        },
        model_dir / "model.joblib",
    )
    (output_dir / "evaluation.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
