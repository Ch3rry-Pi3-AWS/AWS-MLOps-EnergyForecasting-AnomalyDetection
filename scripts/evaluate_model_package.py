"""Evaluate a SageMaker model package and write a promotion report.

This runner consumes Terraform outputs from the model-evaluation module and
the earlier model-registry stage. It resolves a forecast or anomaly model
package, loads the metrics emitted by its SageMaker training job, evaluates
those metrics against the configured thresholds, writes a JSON report to S3,
and can optionally approve the package when it passes.

Notes
-----
- Training scripts already persist `evaluation.json`, so this stage adds the
  missing review and promotion logic rather than retraining anything.
- The report is written to the shared artefact bucket so training outputs,
  evaluation reports, and deployment artefacts stay within the same storage
  boundary.
- Approval remains opt-in because some teams may still want a human review
  even when the automated checks pass.

Examples
--------
Evaluate the latest forecast package and write a report:

>>> # uv run python scripts/evaluate_model_package.py --model-family forecast

Evaluate the latest anomaly package and approve it automatically if it passes:

>>> # uv run python scripts/evaluate_model_package.py --model-family anomaly --approve-if-pass
"""

from __future__ import annotations

import argparse
import io
import json
import os
import subprocess
import sys
import tarfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

try:
    import boto3
except ModuleNotFoundError as exc:  # pragma: no cover - environment guard
    raise SystemExit(
        "boto3 is required to evaluate model packages locally. Install project dependencies with "
        "`uv sync --dev` and then rerun via `uv run python scripts/evaluate_model_package.py`."
    ) from exc


def build_report_key(
    report_prefix: str,
    model_family: str,
    model_package_version: int,
    timestamp_suffix: str,
) -> str:
    """Load the shared evaluation-key helper lazily after `src/` bootstrapping."""

    from energy_forecasting.ml.evaluation import build_evaluation_report_key

    return build_evaluation_report_key(
        report_prefix=report_prefix,
        model_family=model_family,
        model_package_version=model_package_version,
        timestamp_suffix=timestamp_suffix,
    )


def evaluate_family_metrics(model_family: str, metrics: dict[str, object], thresholds: dict[str, float]) -> dict[str, object]:
    """Load the appropriate evaluation helper lazily after `src/` bootstrapping."""

    from energy_forecasting.ml.evaluation import evaluate_anomaly_metrics, evaluate_forecast_metrics

    if model_family == "forecast":
        return evaluate_forecast_metrics(metrics, thresholds)
    if model_family == "anomaly":
        return evaluate_anomaly_metrics(metrics, thresholds)
    raise ValueError(f"Unsupported model family: {model_family}")


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
            "`python scripts\\deploy.py --model-evaluation-only` for the model-evaluation stage."
        )
    return value


def parse_s3_uri(s3_uri: str) -> tuple[str, str]:
    """Split an S3 URI into bucket and key components."""

    parsed = urlparse(s3_uri)
    if parsed.scheme != "s3" or not parsed.netloc:
        raise ValueError(f"Expected an S3 URI, got: {s3_uri}")
    return parsed.netloc, parsed.path.lstrip("/")


def select_model_package_arn(
    sagemaker_client,
    *,
    model_package_group_name: str,
    explicit_model_package_arn: str | None,
) -> str:
    """Resolve the model package ARN to evaluate."""

    if explicit_model_package_arn:
        return explicit_model_package_arn

    response = sagemaker_client.list_model_packages(ModelPackageGroupName=model_package_group_name)
    packages = response.get("ModelPackageSummaryList", [])
    if not packages:
        raise RuntimeError(
            f"No model packages were found in {model_package_group_name}. "
            "Run the appropriate training-and-registration stage first."
        )

    latest_package = max(packages, key=lambda item: item["ModelPackageVersion"])
    return latest_package["ModelPackageArn"]


def read_s3_text(s3_client, *, bucket_name: str, object_key: str) -> str:
    """Read a UTF-8 text object from S3."""

    response = s3_client.get_object(Bucket=bucket_name, Key=object_key)
    return response["Body"].read().decode("utf-8")


def read_evaluation_json_from_tarball(s3_client, *, bucket_name: str, object_key: str) -> dict[str, object]:
    """Extract `evaluation.json` from a SageMaker output tarball stored in S3."""

    response = s3_client.get_object(Bucket=bucket_name, Key=object_key)
    data = response["Body"].read()
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
        for member in archive.getmembers():
            if member.name.endswith("evaluation.json"):
                extracted = archive.extractfile(member)
                if extracted is None:
                    continue
                return json.loads(extracted.read().decode("utf-8"))

    raise FileNotFoundError(f"No evaluation.json file was found inside S3 tarball: s3://{bucket_name}/{object_key}")


def load_training_metrics(
    s3_client,
    *,
    model_artifact_s3_uri: str,
) -> tuple[dict[str, object], str]:
    """
    Load evaluation metrics from the training-job output area in S3.

    Parameters
    ----------
    s3_client : botocore.client.S3
        S3 client used to read training outputs.
    model_artifact_s3_uri : str
        SageMaker model-artifact URI ending in `model.tar.gz`.

    Returns
    -------
    tuple[dict[str, object], str]
        Parsed metrics dictionary and the S3 URI from which it was loaded.
    """

    bucket_name, model_artifact_key = parse_s3_uri(model_artifact_s3_uri)
    output_prefix = model_artifact_key.rsplit("/", 1)[0] + "/"

    response = s3_client.list_objects_v2(Bucket=bucket_name, Prefix=output_prefix)
    keys = [item["Key"] for item in response.get("Contents", [])]

    for key in keys:
        if key.endswith("evaluation.json"):
            return json.loads(read_s3_text(s3_client, bucket_name=bucket_name, object_key=key)), f"s3://{bucket_name}/{key}"

    for key in keys:
        if key.endswith("output.tar.gz"):
            return (
                read_evaluation_json_from_tarball(s3_client, bucket_name=bucket_name, object_key=key),
                f"s3://{bucket_name}/{key}",
            )

    raise FileNotFoundError(
        "Could not find evaluation metrics under the training output prefix "
        f"s3://{bucket_name}/{output_prefix}. Expected either evaluation.json or output.tar.gz."
    )


def upload_report(
    s3_client,
    *,
    bucket_name: str,
    object_key: str,
    kms_key_arn: str,
    report: dict[str, object],
) -> str:
    """Write the structured evaluation report to S3 with KMS encryption."""

    body = json.dumps(report, indent=2).encode("utf-8")
    s3_client.put_object(
        Bucket=bucket_name,
        Key=object_key,
        Body=body,
        ContentType="application/json",
        ServerSideEncryption="aws:kms",
        SSEKMSKeyId=kms_key_arn,
    )
    return f"s3://{bucket_name}/{object_key}"


def build_thresholds(tf_dir: Path, model_family: str) -> dict[str, float]:
    """Load the model-family-specific threshold set from Terraform outputs."""

    if model_family == "forecast":
        return {
            "min_training_rows": float(get_output(tf_dir, "forecast_min_training_rows")),
            "max_mae": float(get_output(tf_dir, "forecast_max_mae")),
            "max_rmse": float(get_output(tf_dir, "forecast_max_rmse")),
            "min_r2": float(get_output(tf_dir, "forecast_min_r2")),
        }
    if model_family == "anomaly":
        return {
            "min_training_rows": float(get_output(tf_dir, "anomaly_min_training_rows")),
            "min_anomaly_rate": float(get_output(tf_dir, "anomaly_min_anomaly_rate")),
            "max_anomaly_rate": float(get_output(tf_dir, "anomaly_max_anomaly_rate")),
        }
    raise ValueError(f"Unsupported model family: {model_family}")


def get_family_outputs(tf_dir: Path, model_family: str) -> tuple[str, str]:
    """Load the model family's registry group name and report prefix."""

    if model_family == "forecast":
        return (
            get_output(tf_dir, "forecast_model_package_group_name"),
            get_output(tf_dir, "forecast_evaluation_report_prefix"),
        )
    if model_family == "anomaly":
        return (
            get_output(tf_dir, "anomaly_model_package_group_name"),
            get_output(tf_dir, "anomaly_evaluation_report_prefix"),
        )
    raise ValueError(f"Unsupported model family: {model_family}")


def main() -> None:
    """Evaluate a model package and optionally approve it when the checks pass."""

    parser = argparse.ArgumentParser(
        description="Evaluate a SageMaker model package and optionally approve it when thresholds pass."
    )
    parser.add_argument(
        "--model-family",
        choices=("forecast", "anomaly"),
        required=True,
        help="Model family whose package group and thresholds should be used.",
    )
    parser.add_argument(
        "--model-package-arn",
        default=None,
        help="Optional explicit model package ARN to evaluate. Defaults to the latest package in the family group.",
    )
    parser.add_argument(
        "--approve-if-pass",
        action="store_true",
        help="Approve the evaluated package automatically when every threshold check passes.",
    )
    args = parser.parse_args()

    repo_root = REPO_ROOT
    load_env_file(repo_root / ".env")

    evaluation_dir = repo_root / "terraform" / "19_sagemaker_model_evaluation"
    region = get_output(evaluation_dir, "evaluation_region")
    kms_key_arn = get_output(evaluation_dir, "evaluation_kms_key_arn")
    artefact_bucket_name = get_output(evaluation_dir, "evaluation_artifact_bucket_name")

    model_package_group_name, report_prefix = get_family_outputs(evaluation_dir, args.model_family)
    thresholds = build_thresholds(evaluation_dir, args.model_family)

    sagemaker_client = boto3.client("sagemaker", region_name=region)
    s3_client = boto3.client("s3", region_name=region)

    model_package_arn = select_model_package_arn(
        sagemaker_client,
        model_package_group_name=model_package_group_name,
        explicit_model_package_arn=args.model_package_arn,
    )
    print(f"Evaluating model package: {model_package_arn}")

    package_description = sagemaker_client.describe_model_package(ModelPackageName=model_package_arn)
    package_version = int(package_description["ModelPackageVersion"])
    customer_metadata = package_description.get("CustomerMetadataProperties", {})
    training_job_name = customer_metadata.get("training_job_name")
    if not training_job_name:
        raise RuntimeError(
            "The model package does not include a training_job_name metadata field. "
            "This evaluation stage expects packages created by the current training runners."
        )

    training_description = sagemaker_client.describe_training_job(TrainingJobName=training_job_name)
    model_artifact_s3_uri = training_description["ModelArtifacts"]["S3ModelArtifacts"]
    metrics, metrics_source_s3_uri = load_training_metrics(
        s3_client,
        model_artifact_s3_uri=model_artifact_s3_uri,
    )

    evaluation_result = evaluate_family_metrics(args.model_family, metrics, thresholds)
    timestamp_suffix = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    report_key = build_report_key(
        report_prefix=report_prefix,
        model_family=args.model_family,
        model_package_version=package_version,
        timestamp_suffix=timestamp_suffix,
    )

    report = {
        "model_family": args.model_family,
        "model_package_arn": model_package_arn,
        "model_package_group_name": model_package_group_name,
        "model_package_version": package_version,
        "model_approval_status_before": package_description.get("ModelApprovalStatus", "Unknown"),
        "training_job_name": training_job_name,
        "training_job_arn": training_description["TrainingJobArn"],
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "thresholds": thresholds,
        "metrics": metrics,
        "metrics_source_s3_uri": metrics_source_s3_uri,
        "evaluation": evaluation_result,
        "recommendation": "approve" if evaluation_result["passed"] else "manual_review",
    }

    report_s3_uri = upload_report(
        s3_client,
        bucket_name=artefact_bucket_name,
        object_key=report_key,
        kms_key_arn=kms_key_arn,
        report=report,
    )
    print(f"Evaluation report written to: {report_s3_uri}")
    print(f"Evaluation passed: {evaluation_result['passed']}")

    if args.approve_if_pass and evaluation_result["passed"]:
        sagemaker_client.update_model_package(
            ModelPackageArn=model_package_arn,
            ModelApprovalStatus="Approved",
        )
        print("Model package approval status updated to Approved.")
    elif args.approve_if_pass:
        print("Approval was requested, but the package did not pass evaluation, so no approval change was made.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("Interrupted by user.")
        sys.exit(130)
