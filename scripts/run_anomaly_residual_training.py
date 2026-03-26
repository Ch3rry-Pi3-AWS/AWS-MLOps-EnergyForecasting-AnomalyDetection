"""Launch a SageMaker anomaly residual-training job and register the result.

This script packages a residual-based anomaly training bundle, uploads it to
the artefact bucket, starts an ephemeral SageMaker training job, and
optionally registers the resulting model package into the existing anomaly
registry.

Examples
--------
Run the full anomaly residual-training-and-registration flow:

>>> # uv run python scripts/run_anomaly_residual_training.py
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tarfile
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

try:
    import boto3
except ModuleNotFoundError as exc:  # pragma: no cover - environment guard
    raise SystemExit(
        "boto3 is required to run anomaly residual training locally. Install project dependencies with "
        "`uv sync --dev` and then rerun via `uv run python scripts/run_anomaly_residual_training.py`."
    ) from exc


def build_training_job_name(base_name: str, timestamp_suffix: str) -> str:
    """Load the shared SageMaker naming helper lazily after `src/` bootstrapping."""

    from energy_forecasting.ml.pipeline import build_timestamped_training_job_name

    return build_timestamped_training_job_name(base_name, timestamp_suffix)


def run_capture_optional(cmd: list[str]) -> str | None:
    """Execute a command and return its stripped stdout, or `None` on failure."""

    try:
        return subprocess.check_output(cmd, text=True).strip()
    except subprocess.CalledProcessError:
        return None


def is_terraform_warning_output(output: str) -> bool:
    """Detect Terraform warning text returned in place of a real output value."""

    stripped = output.strip()
    return "Warning: No outputs found" in stripped or stripped.startswith(("â•·", "Ã¢â€¢Â·"))


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
            "`python scripts\\deploy.py --anomaly-residual-training-only` for the anomaly residual stage."
        )
    return value


def fetch_training_log_tail(logs_client, training_job_name: str, limit: int = 25) -> str:
    """Read the tail of the latest CloudWatch log stream for a SageMaker job."""

    try:
        response = logs_client.describe_log_streams(
            logGroupName="/aws/sagemaker/TrainingJobs",
            logStreamNamePrefix=training_job_name,
            descending=True,
            limit=50,
        )
    except Exception:
        return ""

    streams = response.get("logStreams", [])
    if not streams:
        return ""

    latest_stream = max(
        streams,
        key=lambda stream: stream.get("lastEventTimestamp", stream.get("creationTime", 0)),
    )
    try:
        events_response = logs_client.get_log_events(
            logGroupName="/aws/sagemaker/TrainingJobs",
            logStreamName=latest_stream["logStreamName"],
            limit=limit,
            startFromHead=False,
        )
    except Exception:
        return ""

    messages = [event.get("message", "") for event in events_response.get("events", [])]
    return "\n".join(message for message in messages if message)


def wait_for_training_completion(
    sagemaker_client,
    logs_client,
    training_job_name: str,
    poll_seconds: int,
) -> dict[str, object]:
    """Poll SageMaker until the anomaly residual training job reaches a terminal state."""

    last_status = None
    while True:
        description = sagemaker_client.describe_training_job(TrainingJobName=training_job_name)
        status = description["TrainingJobStatus"]
        if status != last_status:
            print(f"Training job status: {status}")
            last_status = status

        if status == "Completed":
            return description
        if status in {"Failed", "Stopped"}:
            reason = description.get("FailureReason", "Unknown failure")
            log_tail = fetch_training_log_tail(logs_client=logs_client, training_job_name=training_job_name)
            if log_tail:
                print("\nRecent SageMaker training logs:")
                print(log_tail)
            raise RuntimeError(f"Training job ended with status '{status}': {reason}")

        time.sleep(poll_seconds)


def register_model_package(
    sagemaker_client,
    *,
    region: str,
    deployment_name: str,
    model_package_group_name: str,
    source_bundle_s3_uri: str,
    inference_image_uri: str,
    model_data_url: str,
    training_job_name: str,
) -> str:
    """Register the completed anomaly residual model artefact into SageMaker Model Registry."""

    response = sagemaker_client.create_model_package(
        ModelPackageGroupName=model_package_group_name,
        ModelApprovalStatus="PendingManualApproval",
        ModelPackageDescription=(
            f"Residual-scoring anomaly model trained from Gold anomaly features for {deployment_name}."
        ),
        InferenceSpecification={
            "Containers": [
                {
                    "Image": inference_image_uri,
                    "ModelDataUrl": model_data_url,
                    "Environment": {
                        "SAGEMAKER_PROGRAM": "inference.py",
                        "SAGEMAKER_SUBMIT_DIRECTORY": source_bundle_s3_uri,
                        "SAGEMAKER_REGION": region,
                    },
                }
            ],
            "SupportedContentTypes": ["application/json"],
            "SupportedResponseMIMETypes": ["application/json"],
            "SupportedRealtimeInferenceInstanceTypes": ["ml.m5.large", "ml.m5.xlarge"],
            "SupportedTransformInstanceTypes": ["ml.m5.large", "ml.m5.xlarge"],
        },
        CustomerMetadataProperties={
            "deployment_name": deployment_name,
            "training_job_name": training_job_name,
            "anomaly_algorithm": "residual_scoring",
        },
    )
    return response["ModelPackageArn"]


def create_source_bundle(source_dir: Path) -> Path:
    """Create the SageMaker source bundle as a `.tar.gz` archive."""

    temp_file = tempfile.NamedTemporaryFile(suffix=".tar.gz", delete=False)
    archive_path = Path(temp_file.name)
    temp_file.close()

    with tarfile.open(archive_path, mode="w:gz") as archive:
        archive.add(source_dir, arcname=".")

    return archive_path


def upload_source_bundle(
    s3_client,
    *,
    archive_path: Path,
    bucket_name: str,
    object_key: str,
    kms_key_arn: str,
) -> str:
    """Upload the SageMaker source bundle to the artefact bucket."""

    with archive_path.open("rb") as handle:
        s3_client.put_object(
            Bucket=bucket_name,
            Key=object_key,
            Body=handle,
            ServerSideEncryption="aws:kms",
            SSEKMSKeyId=kms_key_arn,
        )

    return f"s3://{bucket_name}/{object_key}"


def main() -> None:
    """Launch the anomaly residual training job and optionally register the result."""

    parser = argparse.ArgumentParser(
        description="Launch a SageMaker anomaly residual-training job and register the resulting model package."
    )
    parser.add_argument("--no-wait", action="store_true", help="Submit the training job and exit immediately.")
    parser.add_argument(
        "--skip-registration",
        action="store_true",
        help="Train the model but do not create a model package in the anomaly registry.",
    )
    parser.add_argument("--instance-type", default="ml.m5.xlarge", help="SageMaker training instance type.")
    parser.add_argument("--volume-size-gb", type=int, default=30, help="Training volume size in GB.")
    parser.add_argument("--max-runtime-seconds", type=int, default=3600, help="Training job timeout in seconds.")
    parser.add_argument("--poll-seconds", type=int, default=60, help="Polling interval while waiting for completion.")
    args = parser.parse_args()

    load_env_file(REPO_ROOT / ".env")

    training_dir = REPO_ROOT / "terraform" / "24_sagemaker_anomaly_residual_training"
    context_dir = REPO_ROOT / "terraform" / "01_project_context"

    region = get_output(training_dir, "anomaly_residual_training_region")
    deployment_name = get_output(context_dir, "deployment_name")
    role_arn = get_output(training_dir, "anomaly_residual_training_role_arn")
    source_bundle_s3_uri = get_output(training_dir, "anomaly_residual_training_source_bundle_s3_uri")
    source_bundle_key = get_output(training_dir, "anomaly_residual_training_source_bundle_key")
    source_dir = Path(get_output(training_dir, "anomaly_residual_training_source_dir"))
    input_s3_uri = get_output(training_dir, "anomaly_residual_training_input_s3_uri")
    output_s3_uri = get_output(training_dir, "anomaly_residual_training_output_s3_uri")
    training_image_uri = get_output(training_dir, "anomaly_residual_training_image_uri")
    inference_image_uri = get_output(training_dir, "anomaly_residual_inference_image_uri")
    model_package_group_name = get_output(training_dir, "anomaly_residual_model_package_group_name")
    job_base_name = get_output(training_dir, "anomaly_residual_training_job_base_name")
    kms_key_arn = get_output(training_dir, "anomaly_residual_training_kms_key_arn")

    training_job_name = build_training_job_name(
        job_base_name,
        datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S"),
    )

    sagemaker_client = boto3.client("sagemaker", region_name=region)
    logs_client = boto3.client("logs", region_name=region)
    s3_client = boto3.client("s3", region_name=region)

    source_bundle_archive = create_source_bundle(source_dir)
    try:
        bucket_name = source_bundle_s3_uri.removeprefix("s3://").split("/", 1)[0]
        source_bundle_s3_uri = upload_source_bundle(
            s3_client,
            archive_path=source_bundle_archive,
            bucket_name=bucket_name,
            object_key=source_bundle_key,
            kms_key_arn=kms_key_arn,
        )
    finally:
        source_bundle_archive.unlink(missing_ok=True)

    print(f"Submitting training job: {training_job_name}")
    sagemaker_client.create_training_job(
        TrainingJobName=training_job_name,
        AlgorithmSpecification={
            "TrainingImage": training_image_uri,
            "TrainingInputMode": "File",
        },
        RoleArn=role_arn,
        InputDataConfig=[
            {
                "ChannelName": "train",
                "DataSource": {
                    "S3DataSource": {
                        "S3DataType": "S3Prefix",
                        "S3Uri": input_s3_uri,
                        "S3DataDistributionType": "FullyReplicated",
                    }
                },
                "ContentType": "application/x-parquet",
                "InputMode": "File",
            }
        ],
        OutputDataConfig={"S3OutputPath": output_s3_uri},
        ResourceConfig={
            "InstanceType": args.instance_type,
            "InstanceCount": 1,
            "VolumeSizeInGB": args.volume_size_gb,
        },
        StoppingCondition={"MaxRuntimeInSeconds": args.max_runtime_seconds},
        HyperParameters={
            "sagemaker_program": "train.py",
            "sagemaker_submit_directory": source_bundle_s3_uri,
            "sagemaker_region": region,
        },
    )

    if args.no_wait:
        print(f"Training job submitted. Check it in SageMaker with name: {training_job_name}")
        return

    description = wait_for_training_completion(
        sagemaker_client=sagemaker_client,
        logs_client=logs_client,
        training_job_name=training_job_name,
        poll_seconds=args.poll_seconds,
    )
    model_data_url = description["ModelArtifacts"]["S3ModelArtifacts"]
    print(f"Training completed. Model artifacts: {model_data_url}")

    if args.skip_registration:
        print("Registration was skipped by request.")
        return

    model_package_arn = register_model_package(
        sagemaker_client,
        region=region,
        deployment_name=deployment_name,
        model_package_group_name=model_package_group_name,
        source_bundle_s3_uri=source_bundle_s3_uri,
        inference_image_uri=inference_image_uri,
        model_data_url=model_data_url,
        training_job_name=training_job_name,
    )
    print(f"Registered model package: {model_package_arn}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("Interrupted by user.")
        sys.exit(130)
