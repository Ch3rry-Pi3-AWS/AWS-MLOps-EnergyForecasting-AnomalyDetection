"""Inference entry point for the dense autoencoder anomaly model package."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd
import torch
from torch import nn


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


def model_fn(model_dir: str) -> dict[str, Any]:
    """Load the persisted autoencoder model bundle from SageMaker model storage."""

    bundle = torch.load(Path(model_dir) / "model.pt", map_location="cpu")
    model = DenseAutoencoder(
        input_dim=int(bundle["input_dim"]),
        hidden_dim=int(bundle["hidden_dim"]),
        latent_dim=int(bundle["latent_dim"]),
    )
    model.load_state_dict(bundle["state_dict"])
    model.eval()
    bundle["model"] = model
    return bundle


def input_fn(request_body: str, content_type: str) -> pd.DataFrame:
    """Parse incoming anomaly-inference payloads into a DataFrame."""

    if content_type != "application/json":
        raise ValueError(f"Unsupported content type: {content_type}")

    payload = json.loads(request_body)
    if isinstance(payload, dict) and "instances" in payload:
        payload = payload["instances"]
    if not isinstance(payload, list):
        raise ValueError("Inference payload must be a list of feature records.")
    return pd.DataFrame(payload)


def predict_fn(input_data: pd.DataFrame, model_bundle: dict[str, Any]) -> list[dict[str, float | bool]]:
    """Run autoencoder inference and return both scores and boolean flags."""

    feature_columns = model_bundle["feature_columns"]
    aligned = input_data.reindex(columns=feature_columns, fill_value=0.0)
    numeric = aligned.apply(pd.to_numeric, errors="coerce").fillna(0.0)

    means = pd.Series(model_bundle["feature_means"], dtype="float64").reindex(feature_columns).fillna(0.0)
    stds = pd.Series(model_bundle["feature_stds"], dtype="float64").reindex(feature_columns).replace(0.0, 1.0).fillna(1.0)
    normalized = ((numeric - means) / stds).astype("float32")

    tensor = torch.tensor(normalized.to_numpy(), dtype=torch.float32)
    with torch.no_grad():
        reconstructed = model_bundle["model"](tensor)
        scores = torch.mean((reconstructed - tensor) ** 2, dim=1).cpu().tolist()

    threshold = float(model_bundle["score_threshold"])
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
