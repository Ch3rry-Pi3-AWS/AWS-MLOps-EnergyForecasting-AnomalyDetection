"""Run repeatable smoke tests against the live SageMaker forecast and anomaly endpoints.

Examples
--------
Run both endpoint smoke tests:

>>> # uv run python scripts/run_endpoint_smoke_tests.py

Run only the forecast endpoint smoke test and print the request payload:

>>> # uv run python scripts/run_endpoint_smoke_tests.py --forecast-only --show-payload
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
    from botocore.config import Config
    from botocore.exceptions import ReadTimeoutError
except ModuleNotFoundError as exc:  # pragma: no cover - environment guard
    raise SystemExit(
        "boto3 is required to run endpoint smoke tests locally. Install project dependencies with "
        "`uv sync --dev` and then rerun via `uv run python scripts/run_endpoint_smoke_tests.py`."
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
    return "Warning: No outputs found" in stripped or stripped.startswith(("Ã¢â€¢Â·", "ÃƒÂ¢Ã¢â‚¬Â¢Ã‚Â·"))


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
            "Reapply the module so its outputs are written to state before running endpoint smoke tests."
        )
    return value


def invoke_json(runtime_client, *, endpoint_name: str, payload: str) -> str:
    """Invoke a SageMaker endpoint with JSON and return the raw response body."""

    try:
        response = runtime_client.invoke_endpoint(
            EndpointName=endpoint_name,
            ContentType="application/json",
            Accept="application/json",
            Body=payload.encode("utf-8"),
        )
    except ReadTimeoutError as exc:
        raise RuntimeError(
            f"Endpoint {endpoint_name} did not respond before the configured runtime read timeout. "
            "The endpoint is likely healthy but serving too slowly for the default smoke-test budget. "
            "Retry with a higher --read-timeout-seconds value."
        ) from exc
    return response["Body"].read().decode("utf-8")


def assert_endpoint_in_service(sagemaker_client, *, endpoint_name: str) -> dict[str, object]:
    """Describe an endpoint and assert that it is ready to serve traffic."""

    description = sagemaker_client.describe_endpoint(EndpointName=endpoint_name)
    status = description["EndpointStatus"]
    if status != "InService":
        raise RuntimeError(f"Endpoint {endpoint_name} is not ready for smoke tests. Current status: {status}")
    return description


def run_forecast_smoke_test(*, show_payload: bool) -> None:
    """Run the live forecast endpoint smoke test against the latest Gold row."""

    from energy_forecasting.ml.endpoint_smoke import (
        build_latest_forecast_deepar_payload,
        build_latest_forecast_sequence_payload,
        build_latest_row_payload_from_s3,
        get_deployed_model_package_arn,
        load_training_metrics_from_model_package,
        validate_forecast_response,
    )

    endpoint_dir = REPO_ROOT / "terraform" / "16_sagemaker_forecast_endpoint"
    training_dir = REPO_ROOT / "terraform" / "14_sagemaker_forecast_training"
    region = get_output(endpoint_dir, "forecast_endpoint_region")
    endpoint_name = get_output(endpoint_dir, "forecast_endpoint_name")
    gold_input_s3_uri = get_output(training_dir, "forecast_training_input_s3_uri")

    sagemaker_client = boto3.client("sagemaker", region_name=region)
    runtime_client = boto3.client(
        "sagemaker-runtime",
        region_name=region,
        config=Config(read_timeout=run_forecast_smoke_test.read_timeout_seconds, connect_timeout=60, retries={"max_attempts": 2}),
    )
    s3_client = boto3.client("s3", region_name=region)

    assert_endpoint_in_service(sagemaker_client, endpoint_name=endpoint_name)
    deployed_model_package_arn = get_deployed_model_package_arn(
        sagemaker_client,
        endpoint_name=endpoint_name,
    )
    forecast_algorithm = "baseline"
    metrics: dict[str, object] = {}
    if deployed_model_package_arn:
        forecast_algorithm, metrics = load_training_metrics_from_model_package(
            sagemaker_client,
            s3_client,
            model_package_arn=deployed_model_package_arn,
        )

    if forecast_algorithm == "tft":
        required_rows = int(metrics.get("context_length", 48)) + int(metrics.get("prediction_length", 48))
        payload, context = build_latest_forecast_sequence_payload(
            s3_client,
            gold_input_s3_uri=gold_input_s3_uri,
            required_rows=required_rows,
        )
    elif forecast_algorithm == "deepar":
        payload, context = build_latest_forecast_deepar_payload(
            s3_client,
            gold_input_s3_uri=gold_input_s3_uri,
            feature_columns=list(metrics.get("feature_columns", [])),
            context_length=int(metrics.get("context_length", 48)),
            prediction_length=int(metrics.get("prediction_length", 48)),
        )
    else:
        payload, context = build_latest_row_payload_from_s3(
            s3_client,
            dataset_s3_uri=gold_input_s3_uri,
            excluded_columns={
                "demand_mw",
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
    body = invoke_json(runtime_client, endpoint_name=endpoint_name, payload=payload)
    validated = validate_forecast_response(body)

    print("Forecast endpoint smoke test passed.")
    print(f"Endpoint: {endpoint_name}")
    print(f"Forecast algorithm: {forecast_algorithm}")
    print("Latest Gold row context:")
    print(json.dumps(context, indent=2))
    if show_payload:
        print("Request payload:")
        print(payload)
    print("Response:")
    print(json.dumps(validated, indent=2))


def run_anomaly_smoke_test(*, show_payload: bool) -> None:
    """Run the live anomaly endpoint smoke test against the latest Gold row."""

    from energy_forecasting.ml.endpoint_smoke import (
        build_latest_row_payload_from_s3,
        validate_anomaly_response,
    )

    endpoint_dir = REPO_ROOT / "terraform" / "17_sagemaker_anomaly_endpoint"
    training_dir = REPO_ROOT / "terraform" / "15_sagemaker_anomaly_training"
    region = get_output(endpoint_dir, "anomaly_endpoint_region")
    endpoint_name = get_output(endpoint_dir, "anomaly_endpoint_name")
    gold_input_s3_uri = get_output(training_dir, "anomaly_training_input_s3_uri")

    sagemaker_client = boto3.client("sagemaker", region_name=region)
    runtime_client = boto3.client(
        "sagemaker-runtime",
        region_name=region,
        config=Config(read_timeout=run_anomaly_smoke_test.read_timeout_seconds, connect_timeout=60, retries={"max_attempts": 2}),
    )
    s3_client = boto3.client("s3", region_name=region)

    assert_endpoint_in_service(sagemaker_client, endpoint_name=endpoint_name)
    payload, context = build_latest_row_payload_from_s3(
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
    body = invoke_json(runtime_client, endpoint_name=endpoint_name, payload=payload)
    validated = validate_anomaly_response(body)

    print("Anomaly endpoint smoke test passed.")
    print(f"Endpoint: {endpoint_name}")
    print("Latest Gold row context:")
    print(json.dumps(context, indent=2))
    if show_payload:
        print("Request payload:")
        print(payload)
    print("Response:")
    print(json.dumps(validated, indent=2))


def main() -> None:
    """Run smoke tests against one or both live endpoints."""

    parser = argparse.ArgumentParser(
        description="Run repeatable smoke tests against the live SageMaker forecast and anomaly endpoints."
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--forecast-only", action="store_true", help="Run only the forecast endpoint smoke test.")
    group.add_argument("--anomaly-only", action="store_true", help="Run only the anomaly endpoint smoke test.")
    parser.add_argument("--show-payload", action="store_true", help="Print request payloads before invocation.")
    parser.add_argument(
        "--read-timeout-seconds",
        type=int,
        default=300,
        help="Botocore read timeout used while waiting for live endpoint responses.",
    )
    args = parser.parse_args()

    load_env_file(REPO_ROOT / ".env")
    run_forecast_smoke_test.read_timeout_seconds = args.read_timeout_seconds
    run_anomaly_smoke_test.read_timeout_seconds = args.read_timeout_seconds

    if args.forecast_only:
        run_forecast_smoke_test(show_payload=args.show_payload)
        return
    if args.anomaly_only:
        run_anomaly_smoke_test(show_payload=args.show_payload)
        return

    run_forecast_smoke_test(show_payload=args.show_payload)
    run_anomaly_smoke_test(show_payload=args.show_payload)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("Interrupted by user.")
        sys.exit(130)
