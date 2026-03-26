"""Invoke the deployed SageMaker anomaly endpoint with a JSON payload.

This helper mirrors the forecast invocation script so the anomaly-serving
contract can be tested directly from the command line.

Examples
--------
Invoke the endpoint with the default minimal payload:

>>> # uv run python scripts/invoke_anomaly_endpoint.py

Invoke using the latest real Gold anomaly-feature row:

>>> # uv run python scripts/invoke_anomaly_endpoint.py --latest-gold-row --show-payload
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent

try:
    import boto3
    from botocore.config import Config
    from botocore.exceptions import ReadTimeoutError
except ModuleNotFoundError as exc:  # pragma: no cover - environment guard
    raise SystemExit(
        "boto3 is required to invoke the anomaly endpoint locally. Install project dependencies with "
        "`uv sync --dev` and then rerun via `uv run python scripts/invoke_anomaly_endpoint.py`."
    ) from exc


def run_capture_optional(cmd: list[str]) -> str | None:
    """Execute a command and return its stripped stdout, or `None` on failure."""

    try:
        return subprocess.check_output(cmd, text=True).strip()
    except subprocess.CalledProcessError:
        return None


def is_terraform_warning_output(output: str) -> bool:
    """Detect Terraform warning text returned in place of a real output value."""

    stripped = output.strip()
    return "Warning: No outputs found" in stripped or stripped.startswith("â•·")


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
    if output and not is_terraform_warning_output(output):
        return output

    value = get_output_from_state(tf_dir, output_name)
    if value is None:
        raise RuntimeError(
            f"Terraform output '{output_name}' was not found in {tf_dir}. "
            "Reapply the module so its outputs are written to state before invoking the endpoint."
        )
    return value


def build_latest_gold_payload(
    s3_client,
    *,
    gold_input_s3_uri: str,
) -> tuple[str, dict[str, Any]]:
    """Build an invocation payload from the latest Gold anomaly-feature row."""

    from energy_forecasting.ml.endpoint_smoke import build_latest_row_payload_from_s3

    return build_latest_row_payload_from_s3(
        s3_client,
        dataset_s3_uri=gold_input_s3_uri,
        excluded_columns={
            "interval_start_utc",
            "interval_end_utc",
            "settlement_date",
            "publish_time_utc",
            "dataset_name",
        },
        context_columns=[
            "interval_start_utc",
            "interval_end_utc",
            "settlement_date",
            "publish_time_utc",
        ],
    )


def load_payload(
    args: argparse.Namespace,
    *,
    s3_client,
    gold_input_s3_uri: str,
) -> tuple[str, dict[str, Any] | None]:
    """Resolve the JSON request body sent to the hosted anomaly endpoint."""

    if args.payload_file:
        return Path(args.payload_file).read_text(encoding="utf-8"), None
    if args.instances_json:
        payload = {"instances": json.loads(args.instances_json)}
        return json.dumps(payload), None
    if args.latest_gold_row:
        return build_latest_gold_payload(s3_client, gold_input_s3_uri=gold_input_s3_uri)
    return json.dumps({"instances": [{}]}), None


def main() -> None:
    """Invoke the anomaly endpoint and print the JSON response."""

    parser = argparse.ArgumentParser(
        description="Invoke the deployed SageMaker anomaly endpoint with a JSON payload."
    )
    parser.add_argument(
        "--payload-file",
        default=None,
        help="Optional path to a JSON payload file to send directly to the endpoint.",
    )
    parser.add_argument(
        "--instances-json",
        default=None,
        help="Optional JSON list of records used to build a payload of the form {'instances': [...]}.",
    )
    parser.add_argument(
        "--latest-gold-row",
        action="store_true",
        help="Build the request payload from the latest Gold anomaly-feature row in S3.",
    )
    parser.add_argument(
        "--show-payload",
        action="store_true",
        help="Print the request payload before invoking the endpoint.",
    )
    parser.add_argument(
        "--read-timeout-seconds",
        type=int,
        default=300,
        help="Botocore read timeout used while waiting for the anomaly endpoint response.",
    )
    args = parser.parse_args()

    selected_payload_modes = sum(
        bool(value) for value in (args.payload_file, args.instances_json, args.latest_gold_row)
    )
    if selected_payload_modes > 1:
        raise ValueError("Use only one of --payload-file, --instances-json, or --latest-gold-row.")

    load_env_file(REPO_ROOT / ".env")
    endpoint_dir = REPO_ROOT / "terraform" / "17_sagemaker_anomaly_endpoint"
    training_dir = REPO_ROOT / "terraform" / "15_sagemaker_anomaly_training"

    region = get_output(endpoint_dir, "anomaly_endpoint_region")
    endpoint_name = get_output(endpoint_dir, "anomaly_endpoint_name")
    gold_input_s3_uri = get_output(training_dir, "anomaly_training_input_s3_uri")
    s3_client = boto3.client("s3", region_name=region)
    payload, payload_context = load_payload(
        args,
        s3_client=s3_client,
        gold_input_s3_uri=gold_input_s3_uri,
    )

    if payload_context is not None:
        print("Latest Gold row context:")
        print(json.dumps(payload_context, indent=2))

    if args.show_payload:
        print("Request payload:")
        print(payload)

    runtime_client = boto3.client(
        "sagemaker-runtime",
        region_name=region,
        config=Config(read_timeout=args.read_timeout_seconds, connect_timeout=60, retries={"max_attempts": 2}),
    )
    try:
        response = runtime_client.invoke_endpoint(
            EndpointName=endpoint_name,
            ContentType="application/json",
            Accept="application/json",
            Body=payload.encode("utf-8"),
        )
    except ReadTimeoutError as exc:
        raise RuntimeError(
            f"Anomaly endpoint {endpoint_name} did not respond before the configured read timeout. "
            "Retry with a higher --read-timeout-seconds value."
        ) from exc
    body = response["Body"].read().decode("utf-8")
    print(body)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("Interrupted by user.")
        sys.exit(130)
