"""Backfill Gold forecast and anomaly rows into SageMaker Feature Store.

Examples
--------
Deploy the Feature Store stage first, then ingest both feature groups:

>>> # uv run python scripts/run_feature_store_ingestion.py
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

try:
    import boto3
    from botocore.exceptions import ClientError
except ModuleNotFoundError as exc:  # pragma: no cover - environment guard
    raise SystemExit(
        "boto3 is required to run Feature Store ingestion locally. Install project dependencies with "
        "`uv sync --dev` and rerun via `uv run python scripts/run_feature_store_ingestion.py`."
    ) from exc

from energy_forecasting.ml.feature_store import (
    build_feature_store_record,
    build_feature_record_id,
    load_gold_feature_rows,
)


def run_capture_optional(cmd: list[str]) -> str | None:
    """Execute a command and return its stripped stdout, or `None` on failure."""

    try:
        return subprocess.check_output(cmd, text=True).strip()
    except subprocess.CalledProcessError:
        return None


def load_env_file(path: Path) -> None:
    """Load simple `KEY=value` pairs from a local `.env` file."""

    if not path.exists():
        return

    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        if key and key not in os.environ:
            os.environ[key.strip()] = value.strip()


def get_output_from_state(tf_dir: Path, output_name: str) -> str | None:
    """Read a Terraform output directly from local state as a fallback."""

    state_path = tf_dir / "terraform.tfstate"
    if not state_path.exists():
        return None

    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None

    outputs = state.get("outputs", {})
    if output_name not in outputs:
        return None

    value = outputs[output_name].get("value")
    if value is None or value == "null":
        return None
    if isinstance(value, (dict, list)):
        return json.dumps(value)
    return str(value)


def get_output(tf_dir: Path, output_name: str) -> str:
    """Read a required Terraform output from CLI output or local state."""

    output = run_capture_optional(["terraform", f"-chdir={tf_dir}", "output", "-raw", output_name])
    if output:
        return output

    value = get_output_from_state(tf_dir, output_name)
    if value is None:
        raise RuntimeError(
            f"Terraform output '{output_name}' was not found in {tf_dir}. "
            "Reapply the module first, for example `python scripts\\deploy.py --feature-store-only`."
        )
    return value


def ensure_feature_group_ready(sagemaker_client, *, feature_group_name: str) -> None:
    """Fail early if the target feature group is not ready for puts."""

    try:
        description = sagemaker_client.describe_feature_group(FeatureGroupName=feature_group_name)
    except ClientError as exc:
        error_code = exc.response.get("Error", {}).get("Code")
        if error_code == "ResourceNotFound":
            raise RuntimeError(
                f"Feature group '{feature_group_name}' was not found. "
                "The Feature Store Terraform apply likely failed or has not been run yet. "
                "Reapply `python scripts\\deploy.py --feature-store-only` after fixing IAM permissions."
            ) from exc
        raise
    status = description["FeatureGroupStatus"]
    if status != "Created":
        raise RuntimeError(
            f"Feature group '{feature_group_name}' is not ready. Current status: {status}. "
            "Wait for the Terraform-created resource to finish provisioning and retry."
        )


def put_rows(
    runtime_client,
    *,
    feature_group_name: str,
    rows: list[dict[str, object]],
    record_identifier_feature_name: str,
) -> None:
    """Upsert Gold rows into a SageMaker Feature Group with progress output."""

    total = len(rows)
    for index, row in enumerate(rows, start=1):
        runtime_client.put_record(
            FeatureGroupName=feature_group_name,
            Record=build_feature_store_record(
                row,
                record_identifier_feature_name=record_identifier_feature_name,
            ),
        )
        if index == 1 or index == total or index % 250 == 0:
            record_id = build_feature_record_id(row)
            print(f"{feature_group_name}: wrote {index}/{total} records (latest record id: {record_id})")


def ingest_feature_group(
    *,
    s3_client,
    sagemaker_client,
    featurestore_runtime_client,
    feature_group_name: str,
    gold_input_s3_uri: str,
    record_identifier_feature_name: str,
    max_records: int | None,
) -> None:
    """Load Gold rows from S3 and write them into one Feature Group."""

    ensure_feature_group_ready(sagemaker_client, feature_group_name=feature_group_name)
    rows = load_gold_feature_rows(
        s3_client,
        dataset_s3_uri=gold_input_s3_uri,
        max_records=max_records,
    )
    print(f"{feature_group_name}: loaded {len(rows)} Gold rows from {gold_input_s3_uri}")
    put_rows(
        featurestore_runtime_client,
        feature_group_name=feature_group_name,
        rows=rows,
        record_identifier_feature_name=record_identifier_feature_name,
    )


def build_parser() -> argparse.ArgumentParser:
    """Create the CLI parser."""

    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--forecast-only", action="store_true", help="Ingest only the forecast feature group.")
    group.add_argument("--anomaly-only", action="store_true", help="Ingest only the anomaly feature group.")
    parser.add_argument(
        "--max-records",
        type=int,
        default=None,
        help="Optionally ingest only the latest N Gold rows into each selected feature group.",
    )
    return parser


def main() -> None:
    """Run the Feature Store backfill flow."""

    load_env_file(REPO_ROOT / ".env")
    args = build_parser().parse_args()
    feature_store_dir = REPO_ROOT / "terraform" / "28_sagemaker_feature_store"

    region = get_output(feature_store_dir, "feature_store_region")
    record_identifier_feature_name = get_output(
        feature_store_dir,
        "feature_store_record_identifier_feature_name",
    )
    forecast_feature_group_name = get_output(feature_store_dir, "forecast_feature_group_name")
    anomaly_feature_group_name = get_output(feature_store_dir, "anomaly_feature_group_name")
    forecast_gold_input_s3_uri = get_output(feature_store_dir, "forecast_feature_store_gold_input_s3_uri")
    anomaly_gold_input_s3_uri = get_output(feature_store_dir, "anomaly_feature_store_gold_input_s3_uri")

    session = boto3.Session(region_name=region)
    s3_client = session.client("s3")
    sagemaker_client = session.client("sagemaker")
    featurestore_runtime_client = session.client("sagemaker-featurestore-runtime")

    if not args.anomaly_only:
        ingest_feature_group(
            s3_client=s3_client,
            sagemaker_client=sagemaker_client,
            featurestore_runtime_client=featurestore_runtime_client,
            feature_group_name=forecast_feature_group_name,
            gold_input_s3_uri=forecast_gold_input_s3_uri,
            record_identifier_feature_name=record_identifier_feature_name,
            max_records=args.max_records,
        )

    if not args.forecast_only:
        ingest_feature_group(
            s3_client=s3_client,
            sagemaker_client=sagemaker_client,
            featurestore_runtime_client=featurestore_runtime_client,
            feature_group_name=anomaly_feature_group_name,
            gold_input_s3_uri=anomaly_gold_input_s3_uri,
            record_identifier_feature_name=record_identifier_feature_name,
            max_records=args.max_records,
        )


if __name__ == "__main__":
    main()
