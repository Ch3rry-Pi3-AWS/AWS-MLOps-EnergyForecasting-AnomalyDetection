"""Invoke the deployed SageMaker forecast endpoint with a JSON payload.

This helper is intentionally lightweight. It reads the stable forecast
endpoint name from Terraform outputs and sends a JSON request body to
SageMaker Runtime so the hosted contract can be tested without opening Studio.

Examples
--------
Invoke the endpoint with the default minimal payload:

>>> # uv run python scripts/invoke_forecast_endpoint.py

Invoke with a custom payload file:

>>> # uv run python scripts/invoke_forecast_endpoint.py --payload-file sample.json
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

try:
    import boto3
except ModuleNotFoundError as exc:  # pragma: no cover - environment guard
    raise SystemExit(
        "boto3 is required to invoke the forecast endpoint locally. Install project dependencies with "
        "`uv sync --dev` and then rerun via `uv run python scripts/invoke_forecast_endpoint.py`."
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


def load_payload(args: argparse.Namespace) -> str:
    """
    Resolve the JSON request body sent to the hosted endpoint.

    Notes
    -----
    The default payload is intentionally minimal. The inference container
    reindexes missing feature columns to the trained feature set and fills any
    absent values with `0.0`, so a single empty record is enough to prove the
    serving contract end to end.
    """

    if args.payload_file:
        return Path(args.payload_file).read_text(encoding="utf-8")
    if args.instances_json:
        payload = {"instances": json.loads(args.instances_json)}
        return json.dumps(payload)
    return json.dumps({"instances": [{}]})


def main() -> None:
    """Invoke the forecast endpoint and print the JSON response."""

    parser = argparse.ArgumentParser(
        description="Invoke the deployed SageMaker forecast endpoint with a JSON payload."
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
        "--show-payload",
        action="store_true",
        help="Print the request payload before invoking the endpoint.",
    )
    args = parser.parse_args()

    if args.payload_file and args.instances_json:
        raise ValueError("Use either --payload-file or --instances-json, not both.")

    load_env_file(REPO_ROOT / ".env")
    endpoint_dir = REPO_ROOT / "terraform" / "16_sagemaker_forecast_endpoint"

    region = get_output(endpoint_dir, "forecast_endpoint_region")
    endpoint_name = get_output(endpoint_dir, "forecast_endpoint_name")
    payload = load_payload(args)

    if args.show_payload:
        print("Request payload:")
        print(payload)

    runtime_client = boto3.client("sagemaker-runtime", region_name=region)
    response = runtime_client.invoke_endpoint(
        EndpointName=endpoint_name,
        ContentType="application/json",
        Accept="application/json",
        Body=payload.encode("utf-8"),
    )
    body = response["Body"].read().decode("utf-8")
    print(body)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("Interrupted by user.")
        sys.exit(130)
