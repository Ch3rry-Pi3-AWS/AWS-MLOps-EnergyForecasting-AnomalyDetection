"""Train a SARIMAX forecast model from Gold forecast features.

This entry point runs inside a SageMaker scikit-learn training container. It
loads the Parquet files that SageMaker places under the training channel,
builds a chronological demand series with exogenous weather and calendar
covariates, and persists both the fitted SARIMAX model and evaluation metrics
for later registration.

Notes
-----
- This stage is intended to be the first genuinely sequential forecast model
  in the project, rather than another row-wise tabular baseline.
- The model uses demand as the endogenous time series and a curated subset of
  known-in-advance covariates as exogenous regressors.
- Seasonal structure is adapted to the amount of history available so early
  development runs can still complete successfully.

Examples
--------
This script is executed by SageMaker rather than directly from the host shell:

>>> # SageMaker launches this via the SARIMAX forecast-training runner.
"""

from __future__ import annotations

import json
import os
import warnings
from pathlib import Path

import joblib
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from statsmodels.tsa.statespace.sarimax import SARIMAX

PREFERRED_EXOGENOUS_COLUMNS = [
    "settlement_period",
    "temperature_2m",
    "relative_humidity_2m",
    "wind_speed_10m",
    "interval_hour",
    "day_of_week",
    "month_of_year",
    "is_weekend",
]


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
        raise FileNotFoundError(f"No Parquet files were found under SARIMAX training input: {root}")

    frames = [pd.read_parquet(path) for path in parquet_files]
    return pd.concat(frames, ignore_index=True)


def build_series_and_exog(frame: pd.DataFrame) -> tuple[pd.Series, pd.DataFrame, list[str]]:
    """
    Derive the endogenous demand series and exogenous regressors.

    Parameters
    ----------
    frame : pandas.DataFrame
        Raw Gold forecast-features frame.

    Returns
    -------
    tuple[pandas.Series, pandas.DataFrame, list[str]]
        Ordered demand series, exogenous feature frame, and selected exogenous
        feature names.
    """

    if "demand_mw" not in frame.columns:
        raise KeyError("Gold forecast-features frame must contain a 'demand_mw' target column.")

    working = frame.dropna(subset=["demand_mw"]).copy()
    if "interval_start_utc" in working.columns:
        working = working.sort_values("interval_start_utc").reset_index(drop=True)

    exogenous_columns = [
        column
        for column in PREFERRED_EXOGENOUS_COLUMNS
        if column in working.columns and pd.api.types.is_numeric_dtype(working[column])
    ]
    exog_frame = working[exogenous_columns].fillna(0.0) if exogenous_columns else pd.DataFrame(index=working.index)
    demand_series = working["demand_mw"].astype(float)
    return demand_series, exog_frame, exogenous_columns


def split_train_test(
    demand_series: pd.Series,
    exog_frame: pd.DataFrame,
) -> tuple[pd.Series, pd.Series, pd.DataFrame | None, pd.DataFrame | None]:
    """
    Perform a chronological split suitable for one-step-ahead forecasting.

    Parameters
    ----------
    demand_series : pandas.Series
        Endogenous demand time series.
    exog_frame : pandas.DataFrame
        Exogenous covariate frame aligned to the demand series.

    Returns
    -------
    tuple[pandas.Series, pandas.Series, pandas.DataFrame | None, pandas.DataFrame | None]
        Training series, test series, training exogenous frame, and test
        exogenous frame.
    """

    row_count = len(demand_series)
    if row_count < 3:
        raise ValueError("At least three forecast rows are required to train and evaluate the SARIMAX model.")

    split_index = row_count - 1 if row_count < 10 else max(int(row_count * 0.8), 1)
    y_train = demand_series.iloc[:split_index]
    y_test = demand_series.iloc[split_index:]

    if exog_frame.empty:
        return y_train, y_test, None, None

    x_train = exog_frame.iloc[:split_index]
    x_test = exog_frame.iloc[split_index:]
    return y_train, y_test, x_train, x_test


def filter_constant_exogenous_columns(
    x_train: pd.DataFrame | None,
    x_test: pd.DataFrame | None,
) -> tuple[pd.DataFrame | None, pd.DataFrame | None, list[str], list[str]]:
    """
    Drop exogenous columns that are constant within the training split.

    Parameters
    ----------
    x_train : pandas.DataFrame | None
        Training exogenous frame.
    x_test : pandas.DataFrame | None
        Holdout exogenous frame aligned to `x_train`.

    Returns
    -------
    tuple[pandas.DataFrame | None, pandas.DataFrame | None, list[str], list[str]]
        Filtered training frame, filtered holdout frame, retained feature
        columns, and dropped constant feature columns.
    """

    if x_train is None or x_train.empty:
        return None, None if x_test is None else x_test, [], []

    retained_columns = [
        column for column in x_train.columns if x_train[column].nunique(dropna=False) > 1
    ]
    dropped_columns = [column for column in x_train.columns if column not in retained_columns]

    if not retained_columns:
        return None, None, [], dropped_columns

    filtered_train = x_train[retained_columns].copy()
    filtered_test = x_test[retained_columns].copy() if x_test is not None else None
    return filtered_train, filtered_test, retained_columns, dropped_columns


def choose_model_orders(training_row_count: int) -> tuple[tuple[int, int, int], tuple[int, int, int, int]]:
    """
    Pick sensible SARIMAX orders for the available training history.

    Parameters
    ----------
    training_row_count : int
        Number of rows in the training split.

    Returns
    -------
    tuple[tuple[int, int, int], tuple[int, int, int, int]]
        Non-seasonal `order` and seasonal `seasonal_order`.
    """

    if training_row_count >= 7 * 48:
        return (2, 0, 1), (1, 0, 1, 48)
    if training_row_count >= 3 * 48:
        return (1, 0, 1), (1, 0, 0, 48)
    return (1, 0, 1), (0, 0, 0, 0)


def fit_sarimax_model(
    y_train: pd.Series,
    x_train: pd.DataFrame | None,
) -> tuple[object, tuple[int, int, int], tuple[int, int, int, int]]:
    """
    Fit the SARIMAX model and return the fitted results object.

    Parameters
    ----------
    y_train : pandas.Series
        Training demand series.
    x_train : pandas.DataFrame | None
        Optional training exogenous frame.

    Returns
    -------
    tuple[object, tuple[int, int, int], tuple[int, int, int, int]]
        Fitted SARIMAX results object, chosen `order`, and chosen
        `seasonal_order`.
    """

    order, seasonal_order = choose_model_orders(len(y_train))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        model = SARIMAX(
            y_train,
            exog=x_train,
            order=order,
            seasonal_order=seasonal_order,
            trend="c",
            enforce_stationarity=False,
            enforce_invertibility=False,
        )
        results = model.fit(disp=False, maxiter=200)
    return results, order, seasonal_order


def calculate_r2(y_true: pd.Series, y_pred: pd.Series) -> float:
    """
    Compute a safe `R^2` value for chronological holdout evaluation.

    Parameters
    ----------
    y_true : pandas.Series
        Ground-truth demand values.
    y_pred : pandas.Series
        Forecasted demand values aligned to `y_true`.

    Returns
    -------
    float
        Standard `R^2` when at least two holdout rows exist, otherwise `0.0`.
    """

    if len(y_true) < 2:
        return 0.0
    return float(r2_score(y_true, y_pred))


def main() -> None:
    """Train the SARIMAX model and write model plus metrics artefacts."""

    train_channel = Path(os.environ.get("SM_CHANNEL_TRAIN", "/opt/ml/input/data/train"))
    model_dir = Path(os.environ.get("SM_MODEL_DIR", "/opt/ml/model"))
    output_dir = Path(os.environ.get("SM_OUTPUT_DATA_DIR", "/opt/ml/output/data"))

    model_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    frame = load_training_frame(train_channel)
    demand_series, exog_frame, exog_columns = build_series_and_exog(frame)
    y_train, y_test, x_train, x_test = split_train_test(demand_series, exog_frame)
    x_train, x_test, exog_columns, dropped_exog_columns = filter_constant_exogenous_columns(x_train, x_test)
    results, order, seasonal_order = fit_sarimax_model(y_train, x_train)

    forecast = results.forecast(steps=len(y_test), exog=x_test)
    metrics = {
        "mae": float(mean_absolute_error(y_test, forecast)),
        "rmse": float(mean_squared_error(y_test, forecast, squared=False)),
        "r2": calculate_r2(y_test, forecast),
        "training_rows": int(len(y_train)),
        "test_rows": int(len(y_test)),
        "feature_columns": exog_columns,
        "dropped_constant_feature_columns": dropped_exog_columns,
        "order": list(order),
        "seasonal_order": list(seasonal_order),
        "forecast_algorithm": "sarimax",
    }

    joblib.dump(
        {
            "model": results,
            "feature_columns": exog_columns,
            "order": list(order),
            "seasonal_order": list(seasonal_order),
        },
        model_dir / "model.joblib",
    )
    (output_dir / "evaluation.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
