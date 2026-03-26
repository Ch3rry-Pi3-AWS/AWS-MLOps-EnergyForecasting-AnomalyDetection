"""Train a dense autoencoder anomaly model from Gold anomaly features."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import pandas as pd
import torch
from torch import nn
from torch.utils.data import DataLoader, TensorDataset

EXCLUDED_COLUMNS = {
    "interval_start_utc",
    "interval_end_utc",
    "settlement_date",
    "dataset_name",
    "publish_time_utc",
    "bronze_ingestion_date",
}


class DenseAutoencoder(nn.Module):
    """Simple fully connected autoencoder for tabular anomaly features."""

    def __init__(self, input_dim: int, hidden_dim: int, latent_dim: int) -> None:
        super().__init__()
        self.encoder = nn.Sequential(
            nn.Linear(input_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, latent_dim),
            nn.ReLU(),
        )
        self.decoder = nn.Sequential(
            nn.Linear(latent_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, input_dim),
        )

    def forward(self, inputs: torch.Tensor) -> torch.Tensor:
        latent = self.encoder(inputs)
        return self.decoder(latent)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train an autoencoder anomaly model from Gold anomaly features.")
    parser.add_argument("--hidden_dim", type=int, default=32)
    parser.add_argument("--latent_dim", type=int, default=8)
    parser.add_argument("--max_epochs", type=int, default=40)
    parser.add_argument("--batch_size", type=int, default=64)
    parser.add_argument("--learning_rate", type=float, default=0.001)
    parser.add_argument("--score_quantile", type=float, default=0.95)
    return parser.parse_args()


def list_parquet_files(root: Path) -> list[Path]:
    return sorted(path for path in root.rglob("*.parquet") if path.is_file())


def load_training_frame(root: Path) -> pd.DataFrame:
    parquet_files = list_parquet_files(root)
    if not parquet_files:
        raise FileNotFoundError(f"No Parquet files were found under anomaly autoencoder training input: {root}")
    frames = [pd.read_parquet(path) for path in parquet_files]
    return pd.concat(frames, ignore_index=True)


def build_feature_frame(frame: pd.DataFrame) -> tuple[pd.DataFrame, list[str], list[str]]:
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
        raise ValueError("No numeric feature columns were available for anomaly autoencoder training.")

    retained_columns = [
        column for column in numeric_columns if working[column].nunique(dropna=False) > 1
    ]
    dropped_columns = [column for column in numeric_columns if column not in retained_columns]
    if not retained_columns:
        raise ValueError("All numeric anomaly-feature columns were constant; autoencoder training cannot proceed.")

    feature_frame = working[retained_columns].apply(pd.to_numeric, errors="coerce").fillna(0.0)
    return feature_frame, retained_columns, dropped_columns


def expand_bootstrap_frame(features: pd.DataFrame, minimum_rows: int = 64) -> pd.DataFrame:
    if len(features) >= minimum_rows:
        return features
    if features.empty:
        raise ValueError("At least one anomaly-feature row is required to train the autoencoder baseline.")
    repeat_factor = -(-minimum_rows // len(features))
    expanded = pd.concat([features] * repeat_factor, ignore_index=True)
    return expanded.iloc[:minimum_rows].copy()


def train_model(
    features: torch.Tensor,
    *,
    input_dim: int,
    hidden_dim: int,
    latent_dim: int,
    max_epochs: int,
    batch_size: int,
    learning_rate: float,
) -> DenseAutoencoder:
    model = DenseAutoencoder(input_dim=input_dim, hidden_dim=hidden_dim, latent_dim=latent_dim)
    dataset = TensorDataset(features)
    dataloader = DataLoader(dataset, batch_size=min(batch_size, len(dataset)), shuffle=True)
    optimizer = torch.optim.Adam(model.parameters(), lr=learning_rate)
    loss_fn = nn.MSELoss()

    model.train()
    for _ in range(max_epochs):
        for (batch,) in dataloader:
            optimizer.zero_grad()
            reconstructed = model(batch)
            loss = loss_fn(reconstructed, batch)
            loss.backward()
            optimizer.step()
    return model


def reconstruction_scores(model: DenseAutoencoder, features: torch.Tensor) -> torch.Tensor:
    model.eval()
    with torch.no_grad():
        reconstructed = model(features)
        errors = torch.mean((reconstructed - features) ** 2, dim=1)
    return errors


def main() -> None:
    args = parse_args()
    train_channel = Path(os.environ.get("SM_CHANNEL_TRAIN", "/opt/ml/input/data/train"))
    model_dir = Path(os.environ.get("SM_MODEL_DIR", "/opt/ml/model"))
    output_dir = Path(os.environ.get("SM_OUTPUT_DATA_DIR", "/opt/ml/output/data"))

    model_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    torch.manual_seed(42)

    frame = load_training_frame(train_channel)
    features, feature_columns, dropped_columns = build_feature_frame(frame)
    expanded_features = expand_bootstrap_frame(features)

    feature_means = expanded_features.mean()
    feature_stds = expanded_features.std(ddof=0).replace(0.0, 1.0)
    normalized_expanded = ((expanded_features - feature_means) / feature_stds).astype("float32")
    normalized_original = ((features - feature_means) / feature_stds).astype("float32")

    expanded_tensor = torch.tensor(normalized_expanded.to_numpy(), dtype=torch.float32)
    original_tensor = torch.tensor(normalized_original.to_numpy(), dtype=torch.float32)

    model = train_model(
        expanded_tensor,
        input_dim=expanded_tensor.shape[1],
        hidden_dim=args.hidden_dim,
        latent_dim=args.latent_dim,
        max_epochs=args.max_epochs,
        batch_size=args.batch_size,
        learning_rate=args.learning_rate,
    )

    scores = reconstruction_scores(model, original_tensor).cpu().tolist()
    score_series = pd.Series(scores, dtype="float64")
    score_threshold = float(score_series.quantile(args.score_quantile))
    predicted_flags = score_series > score_threshold

    metrics = {
        "score_mean": float(score_series.mean()),
        "score_std": float(score_series.std(ddof=0)),
        "score_threshold": score_threshold,
        "training_rows": int(len(features)),
        "bootstrap_training_rows": int(len(expanded_features)),
        "detected_anomaly_rows": int(predicted_flags.sum()),
        "feature_columns": feature_columns,
        "dropped_constant_feature_columns": dropped_columns,
        "hidden_dim": int(args.hidden_dim),
        "latent_dim": int(args.latent_dim),
        "batch_size": int(args.batch_size),
        "max_epochs": int(args.max_epochs),
        "learning_rate": float(args.learning_rate),
        "score_quantile": float(args.score_quantile),
        "anomaly_algorithm": "autoencoder",
    }

    torch.save(
        {
            "state_dict": model.state_dict(),
            "input_dim": int(expanded_tensor.shape[1]),
            "hidden_dim": int(args.hidden_dim),
            "latent_dim": int(args.latent_dim),
            "feature_columns": feature_columns,
            "dropped_constant_feature_columns": dropped_columns,
            "feature_means": feature_means.to_dict(),
            "feature_stds": feature_stds.to_dict(),
            "score_threshold": score_threshold,
            "anomaly_algorithm": "autoencoder",
        },
        model_dir / "model.pt",
    )
    (output_dir / "evaluation.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
