"""Deploy the latest approved anomaly model package to a SageMaker endpoint.

This script consumes Terraform outputs from the anomaly-endpoint module and
the earlier SageMaker registry stage. It resolves the latest approved model
package in the anomaly registry, creates a concrete SageMaker model and
endpoint configuration, and then creates or updates the stable anomaly
endpoint.

Notes
-----
- Terraform holds the durable endpoint naming and sizing configuration.
- This runner handles model-package selection because "latest approved model"
  is an operational choice rather than static infrastructure.
- The script expects at least one approved model package in the anomaly
  registry. If none exist, approve a registered version first in Studio or via
  the SageMaker API.

Examples
--------
Deploy the latest approved anomaly model and wait for the endpoint:

>>> # uv run python scripts/deploy_anomaly_endpoint.py

Submit the create or update request and return immediately:

>>> # uv run python scripts/deploy_anomaly_endpoint.py --no-wait
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from energy_forecasting.ml.pipeline import build_timestamped_sagemaker_name

try:
    import boto3
    from botocore.exceptions import ClientError
except ModuleNotFoundError as exc:  # pragma: no cover - environment guard
    raise SystemExit(
        "boto3 is required to deploy the anomaly endpoint locally. Install project dependencies with "
        "`uv sync --dev` and then rerun via `uv run python scripts/deploy_anomaly_endpoint.py`."
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
            "Reapply the module so its outputs are written to state, for example "
            "`python scripts\\deploy.py --anomaly-endpoint-only` for the anomaly-endpoint stage."
        )
    return value


def get_latest_approved_model_package_arn(sagemaker_client, model_package_group_name: str) -> str:
    """
    Resolve the newest approved model package in the anomaly registry.

    Parameters
    ----------
    sagemaker_client : botocore.client.SageMaker
        SageMaker client used for registry lookups.
    model_package_group_name : str
        Anomaly model package group name.

    Returns
    -------
    str
        ARN of the latest approved model package.
    """

    response = sagemaker_client.list_model_packages(
        ModelPackageGroupName=model_package_group_name,
        ModelApprovalStatus="Approved",
        SortBy="CreationTime",
        SortOrder="Descending",
        MaxResults=1,
    )
    packages = response.get("ModelPackageSummaryList", [])
    if not packages:
        raise RuntimeError(
            "No approved anomaly model packages were found. Approve a registered model version in Studio "
            "or via `aws sagemaker update-model-package --model-approval-status Approved ...` before deploying."
        )
    return packages[0]["ModelPackageArn"]


def describe_endpoint_optional(sagemaker_client, endpoint_name: str) -> dict[str, object] | None:
    """Return the endpoint description when it exists, otherwise `None`."""

    try:
        return sagemaker_client.describe_endpoint(EndpointName=endpoint_name)
    except ClientError as exc:
        error_code = exc.response.get("Error", {}).get("Code", "")
        if error_code in {"ValidationException", "ResourceNotFound"}:
            return None
        return None


def wait_for_endpoint_in_service(
    sagemaker_client,
    endpoint_name: str,
    poll_seconds: int,
) -> dict[str, object]:
    """Poll SageMaker until the endpoint reaches a terminal deployment state."""

    last_status = None
    while True:
        description = sagemaker_client.describe_endpoint(EndpointName=endpoint_name)
        status = description["EndpointStatus"]
        if status != last_status:
            print(f"Endpoint status: {status}")
            last_status = status

        if status == "InService":
            return description
        if status in {"Failed", "OutOfService"}:
            failure_reason = description.get("FailureReason", "Unknown endpoint deployment failure")
            raise RuntimeError(f"Endpoint deployment failed with status '{status}': {failure_reason}")

        time.sleep(poll_seconds)


def main() -> None:
    """Deploy the latest approved anomaly model package to the stable endpoint."""

    parser = argparse.ArgumentParser(
        description="Deploy the latest approved anomaly model package to a SageMaker endpoint."
    )
    parser.add_argument(
        "--model-package-arn",
        default=None,
        help="Optional explicit model package ARN. If omitted, the latest approved anomaly package is used.",
    )
    parser.add_argument("--no-wait", action="store_true", help="Submit the endpoint create or update request and exit immediately.")
    parser.add_argument("--poll-seconds", type=int, default=60, help="Polling interval while waiting for the endpoint.")
    args = parser.parse_args()

    repo_root = REPO_ROOT
    load_env_file(repo_root / ".env")

    endpoint_dir = repo_root / "terraform" / "17_sagemaker_anomaly_endpoint"

    region = get_output(endpoint_dir, "anomaly_endpoint_region")
    endpoint_name = get_output(endpoint_dir, "anomaly_endpoint_name")
    model_name_base = get_output(endpoint_dir, "anomaly_endpoint_model_name_base")
    endpoint_config_name_base = get_output(endpoint_dir, "anomaly_endpoint_config_name_base")
    instance_type = get_output(endpoint_dir, "anomaly_endpoint_instance_type")
    initial_instance_count = int(get_output(endpoint_dir, "anomaly_endpoint_initial_instance_count"))
    variant_name = get_output(endpoint_dir, "anomaly_endpoint_variant_name")
    kms_key_arn = get_output(endpoint_dir, "anomaly_endpoint_kms_key_arn")
    role_arn = get_output(endpoint_dir, "anomaly_endpoint_role_arn")
    model_package_group_name = get_output(endpoint_dir, "anomaly_model_package_group_name")

    sagemaker_client = boto3.client("sagemaker", region_name=region)
    deployment_suffix = time.strftime("%Y%m%d%H%M%S", time.gmtime())

    model_package_arn = args.model_package_arn or get_latest_approved_model_package_arn(
        sagemaker_client,
        model_package_group_name,
    )
    model_name = build_timestamped_sagemaker_name(model_name_base, deployment_suffix)
    endpoint_config_name = build_timestamped_sagemaker_name(endpoint_config_name_base, deployment_suffix)

    print(f"Using model package: {model_package_arn}")
    print(f"Creating SageMaker model: {model_name}")
    sagemaker_client.create_model(
        ModelName=model_name,
        ExecutionRoleArn=role_arn,
        PrimaryContainer={
            "ModelPackageName": model_package_arn,
        },
    )

    print(f"Creating endpoint configuration: {endpoint_config_name}")
    sagemaker_client.create_endpoint_config(
        EndpointConfigName=endpoint_config_name,
        KmsKeyId=kms_key_arn,
        ProductionVariants=[
            {
                "VariantName": variant_name,
                "ModelName": model_name,
                "InitialInstanceCount": initial_instance_count,
                "InstanceType": instance_type,
                "InitialVariantWeight": 1.0,
            }
        ],
    )

    existing_endpoint = describe_endpoint_optional(sagemaker_client, endpoint_name)
    if existing_endpoint:
        print(f"Updating endpoint: {endpoint_name}")
        sagemaker_client.update_endpoint(
            EndpointName=endpoint_name,
            EndpointConfigName=endpoint_config_name,
        )
    else:
        print(f"Creating endpoint: {endpoint_name}")
        sagemaker_client.create_endpoint(
            EndpointName=endpoint_name,
            EndpointConfigName=endpoint_config_name,
        )

    if args.no_wait:
        print(f"Endpoint deployment submitted for: {endpoint_name}")
        return

    description = wait_for_endpoint_in_service(
        sagemaker_client=sagemaker_client,
        endpoint_name=endpoint_name,
        poll_seconds=args.poll_seconds,
    )
    print(f"Endpoint is InService: {description['EndpointArn']}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("Interrupted by user.")
        sys.exit(130)
