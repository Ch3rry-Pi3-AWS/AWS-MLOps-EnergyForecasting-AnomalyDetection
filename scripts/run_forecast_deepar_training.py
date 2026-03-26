"""Launch a SageMaker DeepAR forecast-training job and register the result.

This runner prepares the row-wise Gold forecast dataset into the JSON Lines
format expected by the built-in SageMaker DeepAR algorithm, launches the
training job, performs a temporary post-training forecast for holdout
evaluation, writes `evaluation.json` back into the training output prefix, and
then registers the resulting model package.

Examples
--------
Run the full DeepAR training-and-registration flow:

>>> # uv run python scripts/run_forecast_deepar_training.py

Submit only the training job and return immediately:

>>> # uv run python scripts/run_forecast_deepar_training.py --no-wait
"""

from __future__ import annotations

import argparse
import gzip
import json
import math
import os
import subprocess
import sys
import tempfile
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

try:
    import boto3
    import pyarrow as pa
    import pyarrow.parquet as pq
except ModuleNotFoundError as exc:  # pragma: no cover - environment guard
    raise SystemExit(
        "boto3 and pyarrow are required to run DeepAR forecast training locally. "
        "Install project dependencies with `uv sync --dev` and then rerun via "
        "`uv run python scripts/run_forecast_deepar_training.py`."
    ) from exc


PREFERRED_DYNAMIC_FEATURE_COLUMNS = [
    "settlement_period",
    "temperature_2m",
    "relative_humidity_2m",
    "wind_speed_10m",
    "interval_hour",
    "day_of_week",
    "month_of_year",
    "is_weekend",
]


def build_timestamped_name(base_name: str, timestamp_suffix: str) -> str:
    """Load the shared SageMaker naming helper lazily after `src/` bootstrapping."""

    from energy_forecasting.ml.pipeline import build_timestamped_sagemaker_name

    return build_timestamped_sagemaker_name(base_name, timestamp_suffix)


def build_training_job_name(base_name: str, timestamp_suffix: str) -> str:
    """Load the shared SageMaker training-name helper lazily after `src/` bootstrapping."""

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
    return "Warning: No outputs found" in stripped or stripped.startswith(("╷", "â•·"))


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
            "`python scripts\\deploy.py --forecast-deepar-training-only` for the DeepAR training stage."
        )
    return value


def parse_s3_uri(s3_uri: str) -> tuple[str, str]:
    """Split an S3 URI into bucket and key components."""

    parsed = urlparse(s3_uri)
    if parsed.scheme != "s3" or not parsed.netloc:
        raise ValueError(f"Expected an S3 URI, got: {s3_uri}")
    return parsed.netloc, parsed.path.lstrip("/")


def list_s3_keys(s3_client, *, bucket_name: str, prefix: str) -> list[str]:
    """List all S3 object keys under a prefix."""

    paginator = s3_client.get_paginator("list_objects_v2")
    keys: list[str] = []
    for page in paginator.paginate(Bucket=bucket_name, Prefix=prefix):
        for item in page.get("Contents", []):
            keys.append(item["Key"])
    return keys


def download_s3_prefix(s3_client, *, bucket_name: str, prefix: str, destination_dir: Path) -> list[Path]:
    """Download all Parquet objects under an S3 prefix into a local temp directory."""

    local_paths: list[Path] = []
    for key in list_s3_keys(s3_client, bucket_name=bucket_name, prefix=prefix):
        if not key.endswith(".parquet"):
            continue
        relative_path = key[len(prefix) :].lstrip("/")
        local_path = destination_dir / relative_path
        local_path.parent.mkdir(parents=True, exist_ok=True)
        s3_client.download_file(bucket_name, key, str(local_path))
        local_paths.append(local_path)
    return sorted(local_paths)


def safe_float(value: Any) -> float:
    """Convert numeric-like values into floats, treating missing values as zero."""

    if value is None:
        return 0.0
    if isinstance(value, float) and math.isnan(value):
        return 0.0
    return float(value)


def format_start_timestamp(value: Any) -> str:
    """Render a DeepAR-compatible start timestamp without timezone information."""

    if value is None:
        raise ValueError("DeepAR input rows require an interval_start_utc value.")
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            value = value.astimezone(timezone.utc).replace(tzinfo=None)
        return value.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day).strftime("%Y-%m-%d %H:%M:%S")

    text = str(value).replace("T", " ").replace("Z", "")
    if "+" in text:
        text = text.split("+", 1)[0]
    if "." in text:
        text = text.split(".", 1)[0]
    return text


def forecast_row_sort_key(row: dict[str, Any]) -> tuple[str, int]:
    """Build a deterministic chronological sort key for Gold forecast rows."""

    timestamp = format_start_timestamp(row.get("interval_start_utc"))
    settlement_period = int(safe_float(row.get("settlement_period")))
    return timestamp, settlement_period


def load_gold_forecast_rows(s3_client, *, gold_input_s3_uri: str) -> list[dict[str, Any]]:
    """Load and chronologically sort Gold forecast-feature rows from S3 Parquet fragments."""

    bucket_name, prefix = parse_s3_uri(gold_input_s3_uri)
    with tempfile.TemporaryDirectory() as temp_dir_name:
        temp_dir = Path(temp_dir_name)
        parquet_files = download_s3_prefix(
            s3_client,
            bucket_name=bucket_name,
            prefix=prefix,
            destination_dir=temp_dir,
        )
        if not parquet_files:
            raise FileNotFoundError(f"No Parquet files were found under DeepAR Gold input: {gold_input_s3_uri}")

        tables = [pq.read_table(path) for path in parquet_files]
        merged = pa.concat_tables(tables, promote_options="default")
        row_dict = merged.to_pydict()
        row_count = merged.num_rows
        rows = [{column: row_dict[column][idx] for column in row_dict} for idx in range(row_count)]

    filtered_rows = [row for row in rows if row.get("demand_mw") is not None]
    filtered_rows.sort(key=forecast_row_sort_key)
    return filtered_rows


def build_deepar_series(rows: list[dict[str, Any]]) -> tuple[str, list[float], list[list[float]], list[str], list[str]]:
    """Convert row-wise Gold features into a single DeepAR target series plus dynamic features."""

    if not rows:
        raise ValueError("No Gold forecast rows were available for DeepAR training.")

    start = format_start_timestamp(rows[0].get("interval_start_utc"))
    target = [safe_float(row.get("demand_mw")) for row in rows]

    retained_columns: list[str] = []
    dropped_constant_columns: list[str] = []
    dynamic_feature_series: list[list[float]] = []

    for column in PREFERRED_DYNAMIC_FEATURE_COLUMNS:
        series = [safe_float(row.get(column)) for row in rows if column in row]
        if len(series) != len(rows):
            continue
        if len(set(series)) <= 1:
            dropped_constant_columns.append(column)
            continue
        retained_columns.append(column)
        dynamic_feature_series.append(series)

    return start, target, dynamic_feature_series, retained_columns, dropped_constant_columns


def split_train_and_holdout(
    target: list[float],
    dynamic_feat: list[list[float]],
    *,
    prediction_length: int,
) -> tuple[list[float], list[float], list[list[float]], list[list[float]]]:
    """Split the series into a training prefix and a forecast holdout horizon."""

    if len(target) <= prediction_length:
        raise ValueError(
            "DeepAR requires more target observations than the configured prediction_length."
        )

    split_index = len(target) - prediction_length
    train_target = target[:split_index]
    holdout_target = target[split_index:]
    train_dynamic_feat = [series[: len(train_target)] for series in dynamic_feat]
    full_dynamic_feat = [series[:] for series in dynamic_feat]
    return train_target, holdout_target, train_dynamic_feat, full_dynamic_feat


def build_training_record(
    *,
    start: str,
    train_target: list[float],
    train_dynamic_feat: list[list[float]],
) -> dict[str, Any]:
    """Build a DeepAR training record."""

    record: dict[str, Any] = {
        "start": start,
        "target": train_target,
    }
    if train_dynamic_feat:
        record["dynamic_feat"] = train_dynamic_feat
    return record


def build_test_record(
    *,
    start: str,
    full_target: list[float],
    full_dynamic_feat: list[list[float]],
) -> dict[str, Any]:
    """Build a DeepAR test-channel record using the full observed series."""

    record: dict[str, Any] = {
        "start": start,
        "target": full_target,
    }
    if full_dynamic_feat:
        record["dynamic_feat"] = full_dynamic_feat
    return record


def write_json_lines_gzip(path: Path, records: list[dict[str, Any]]) -> None:
    """Write JSON Lines records to a gzip-compressed file."""

    with gzip.open(path, mode="wt", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record) + "\n")


def upload_file_to_s3(
    s3_client,
    *,
    local_path: Path,
    bucket_name: str,
    object_key: str,
    kms_key_arn: str,
    content_type: str,
) -> str:
    """Upload a local file to S3 with KMS encryption."""

    with local_path.open("rb") as handle:
        s3_client.put_object(
            Bucket=bucket_name,
            Key=object_key,
            Body=handle,
            ContentType=content_type,
            ServerSideEncryption="aws:kms",
            SSEKMSKeyId=kms_key_arn,
        )
    return f"s3://{bucket_name}/{object_key}"


def wait_for_training_completion(
    sagemaker_client,
    logs_client,
    training_job_name: str,
    poll_seconds: int,
) -> dict[str, Any]:
    """Poll SageMaker until the training job reaches a terminal state."""

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
    stream_name = latest_stream["logStreamName"]
    try:
        events_response = logs_client.get_log_events(
            logGroupName="/aws/sagemaker/TrainingJobs",
            logStreamName=stream_name,
            limit=limit,
            startFromHead=False,
        )
    except Exception:
        return ""

    messages = [event.get("message", "") for event in events_response.get("events", [])]
    return "\n".join(message for message in messages if message)


def wait_for_endpoint_status(sagemaker_client, endpoint_name: str, poll_seconds: int) -> dict[str, Any]:
    """Poll SageMaker until a temporary evaluation endpoint reaches a terminal state."""

    last_status = None
    while True:
        description = sagemaker_client.describe_endpoint(EndpointName=endpoint_name)
        status = description["EndpointStatus"]
        if status != last_status:
            print(f"Evaluation endpoint status: {status}")
            last_status = status

        if status == "InService":
            return description
        if status in {"Failed", "OutOfService"}:
            raise RuntimeError(
                f"DeepAR evaluation endpoint '{endpoint_name}' ended with status '{status}': "
                f"{description.get('FailureReason', 'Unknown failure')}"
            )
        time.sleep(poll_seconds)


def wait_for_endpoint_deleted(sagemaker_client, endpoint_name: str, poll_seconds: int) -> None:
    """Wait until a SageMaker endpoint has been deleted."""

    while True:
        try:
            sagemaker_client.describe_endpoint(EndpointName=endpoint_name)
        except Exception as exc:
            if "Could not find endpoint" in str(exc):
                return
            raise
        time.sleep(poll_seconds)


def create_temporary_evaluation_endpoint(
    sagemaker_client,
    *,
    model_name: str,
    endpoint_config_name: str,
    endpoint_name: str,
    image_uri: str,
    model_data_url: str,
    role_arn: str,
    instance_type: str,
    kms_key_arn: str,
) -> None:
    """Create a temporary SageMaker endpoint used to evaluate the DeepAR model."""

    sagemaker_client.create_model(
        ModelName=model_name,
        ExecutionRoleArn=role_arn,
        PrimaryContainer={
            "Image": image_uri,
            "ModelDataUrl": model_data_url,
        },
    )
    sagemaker_client.create_endpoint_config(
        EndpointConfigName=endpoint_config_name,
        ProductionVariants=[
            {
                "VariantName": "AllTraffic",
                "ModelName": model_name,
                "InitialInstanceCount": 1,
                "InstanceType": instance_type,
                "InitialVariantWeight": 1.0,
            }
        ],
        KmsKeyId=kms_key_arn,
    )
    sagemaker_client.create_endpoint(
        EndpointName=endpoint_name,
        EndpointConfigName=endpoint_config_name,
    )


def cleanup_temporary_evaluation_endpoint(
    sagemaker_client,
    *,
    model_name: str,
    endpoint_config_name: str,
    endpoint_name: str,
    poll_seconds: int,
) -> None:
    """Best-effort cleanup for temporary SageMaker evaluation resources."""

    try:
        sagemaker_client.delete_endpoint(EndpointName=endpoint_name)
        wait_for_endpoint_deleted(sagemaker_client, endpoint_name, poll_seconds)
    except Exception:
        pass

    try:
        sagemaker_client.delete_endpoint_config(EndpointConfigName=endpoint_config_name)
    except Exception:
        pass

    try:
        sagemaker_client.delete_model(ModelName=model_name)
    except Exception:
        pass


def invoke_deepar_endpoint(
    runtime_client,
    *,
    endpoint_name: str,
    train_record: dict[str, Any],
    prediction_length: int,
    full_dynamic_feat: list[list[float]],
) -> list[float]:
    """Invoke the temporary DeepAR endpoint and return the mean forecast horizon."""

    instance: dict[str, Any] = {
        "start": train_record["start"],
        "target": train_record["target"],
    }
    if full_dynamic_feat:
        instance["dynamic_feat"] = full_dynamic_feat

    payload = {
        "instances": [instance],
        "configuration": {
            "num_samples": 100,
            "output_types": ["mean"],
        },
    }
    response = runtime_client.invoke_endpoint(
        EndpointName=endpoint_name,
        ContentType="application/json",
        Accept="application/json",
        Body=json.dumps(payload).encode("utf-8"),
    )
    body = json.loads(response["Body"].read().decode("utf-8"))
    predictions = body["predictions"][0]["mean"]
    return [float(value) for value in predictions[:prediction_length]]


def mean_absolute_error(y_true: list[float], y_pred: list[float]) -> float:
    """Compute mean absolute error without external numeric dependencies."""

    return sum(abs(true - pred) for true, pred in zip(y_true, y_pred, strict=True)) / len(y_true)


def root_mean_squared_error(y_true: list[float], y_pred: list[float]) -> float:
    """Compute RMSE without external numeric dependencies."""

    mse = sum((true - pred) ** 2 for true, pred in zip(y_true, y_pred, strict=True)) / len(y_true)
    return math.sqrt(mse)


def r2_score(y_true: list[float], y_pred: list[float]) -> float:
    """Compute a simple coefficient of determination for the holdout horizon."""

    if len(y_true) < 2:
        return 0.0
    mean_target = sum(y_true) / len(y_true)
    total_sum_squares = sum((value - mean_target) ** 2 for value in y_true)
    if total_sum_squares == 0:
        return 0.0
    residual_sum_squares = sum((true - pred) ** 2 for true, pred in zip(y_true, y_pred, strict=True))
    return 1.0 - (residual_sum_squares / total_sum_squares)


def write_evaluation_json(
    s3_client,
    *,
    model_data_url: str,
    kms_key_arn: str,
    metrics: dict[str, Any],
) -> str:
    """Write `evaluation.json` into the DeepAR training output prefix for stage 19."""

    bucket_name, model_artifact_key = parse_s3_uri(model_data_url)
    evaluation_key = model_artifact_key.rsplit("/", 1)[0] + "/evaluation.json"
    s3_client.put_object(
        Bucket=bucket_name,
        Key=evaluation_key,
        Body=json.dumps(metrics, indent=2).encode("utf-8"),
        ContentType="application/json",
        ServerSideEncryption="aws:kms",
        SSEKMSKeyId=kms_key_arn,
    )
    return f"s3://{bucket_name}/{evaluation_key}"


def register_model_package(
    sagemaker_client,
    *,
    deployment_name: str,
    model_package_group_name: str,
    inference_image_uri: str,
    model_data_url: str,
    training_job_name: str,
) -> str:
    """Register the completed DeepAR model package in SageMaker Model Registry."""

    response = sagemaker_client.create_model_package(
        ModelPackageGroupName=model_package_group_name,
        ModelApprovalStatus="PendingManualApproval",
        ModelPackageDescription=(
            f"DeepAR forecast model trained from Gold forecast features for {deployment_name}."
        ),
        InferenceSpecification={
            "Containers": [
                {
                    "Image": inference_image_uri,
                    "ModelDataUrl": model_data_url,
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
            "forecast_algorithm": "deepar",
        },
    )
    return response["ModelPackageArn"]


def main() -> None:
    """Prepare DeepAR data, launch training, evaluate the holdout, and register the result."""

    parser = argparse.ArgumentParser(
        description="Launch a SageMaker DeepAR forecast-training job and register the resulting model package."
    )
    parser.add_argument("--no-wait", action="store_true", help="Submit the training job and exit immediately.")
    parser.add_argument(
        "--skip-registration",
        action="store_true",
        help="Train and evaluate the model but do not create a model package in the forecast registry.",
    )
    parser.add_argument("--instance-type", default="ml.m5.xlarge", help="SageMaker training instance type.")
    parser.add_argument(
        "--evaluation-instance-type",
        default="ml.m5.large",
        help="Temporary endpoint instance type used for post-training DeepAR evaluation.",
    )
    parser.add_argument("--volume-size-gb", type=int, default=30, help="Training volume size in GB.")
    parser.add_argument("--max-runtime-seconds", type=int, default=7200, help="Training job timeout in seconds.")
    parser.add_argument("--poll-seconds", type=int, default=60, help="Polling interval while waiting for completion.")
    args = parser.parse_args()

    load_env_file(REPO_ROOT / ".env")

    training_dir = REPO_ROOT / "terraform" / "22_sagemaker_forecast_deepar_training"
    context_dir = REPO_ROOT / "terraform" / "01_project_context"

    region = get_output(training_dir, "forecast_deepar_training_region")
    deployment_name = get_output(context_dir, "deployment_name")
    role_arn = get_output(training_dir, "forecast_deepar_training_role_arn")
    gold_input_s3_uri = get_output(training_dir, "forecast_deepar_gold_input_s3_uri")
    prepared_input_s3_uri = get_output(training_dir, "forecast_deepar_prepared_input_s3_uri")
    training_output_s3_uri = get_output(training_dir, "forecast_deepar_training_output_s3_uri")
    training_image_uri = get_output(training_dir, "forecast_deepar_training_image_uri")
    inference_image_uri = get_output(training_dir, "forecast_deepar_inference_image_uri")
    model_package_group_name = get_output(training_dir, "forecast_deepar_model_package_group_name")
    job_base_name = get_output(training_dir, "forecast_deepar_training_job_base_name")
    kms_key_arn = get_output(training_dir, "forecast_deepar_training_kms_key_arn")
    prediction_length = int(float(get_output(training_dir, "forecast_deepar_prediction_length")))
    context_length = int(float(get_output(training_dir, "forecast_deepar_context_length")))
    time_freq = get_output(training_dir, "forecast_deepar_time_freq")
    epochs = int(float(get_output(training_dir, "forecast_deepar_epochs")))
    num_layers = int(float(get_output(training_dir, "forecast_deepar_num_layers")))
    num_cells = int(float(get_output(training_dir, "forecast_deepar_num_cells")))
    mini_batch_size = int(float(get_output(training_dir, "forecast_deepar_mini_batch_size")))
    likelihood = get_output(training_dir, "forecast_deepar_likelihood")
    temporary_model_base_name = get_output(training_dir, "forecast_deepar_temporary_model_base_name")
    temporary_endpoint_base_name = get_output(training_dir, "forecast_deepar_temporary_endpoint_base_name")
    temporary_endpoint_cfg_base = get_output(training_dir, "forecast_deepar_temporary_endpoint_config_base_name")

    sagemaker_client = boto3.client("sagemaker", region_name=region)
    runtime_client = boto3.client("sagemaker-runtime", region_name=region)
    logs_client = boto3.client("logs", region_name=region)
    s3_client = boto3.client("s3", region_name=region)

    rows = load_gold_forecast_rows(s3_client, gold_input_s3_uri=gold_input_s3_uri)
    start, full_target, full_dynamic_feat, feature_columns, dropped_constant_feature_columns = build_deepar_series(rows)
    train_target, holdout_target, train_dynamic_feat, full_dynamic_feat = split_train_and_holdout(
        full_target,
        full_dynamic_feat,
        prediction_length=prediction_length,
    )

    train_record = build_training_record(
        start=start,
        train_target=train_target,
        train_dynamic_feat=train_dynamic_feat,
    )
    test_record = build_test_record(
        start=start,
        full_target=full_target,
        full_dynamic_feat=full_dynamic_feat,
    )

    train_input_prefix = prepared_input_s3_uri.rstrip("/") + "/train"
    test_input_prefix = prepared_input_s3_uri.rstrip("/") + "/test"
    train_bucket_name, train_prefix = parse_s3_uri(train_input_prefix)
    test_bucket_name, test_prefix = parse_s3_uri(test_input_prefix)

    timestamp_suffix = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    training_job_name = build_training_job_name(job_base_name, timestamp_suffix)

    with tempfile.TemporaryDirectory() as temp_dir_name:
        temp_dir = Path(temp_dir_name)
        train_path = temp_dir / "train.json.gz"
        test_path = temp_dir / "test.json.gz"
        write_json_lines_gzip(train_path, [train_record])
        write_json_lines_gzip(test_path, [test_record])

        train_s3_uri = upload_file_to_s3(
            s3_client,
            local_path=train_path,
            bucket_name=train_bucket_name,
            object_key=f"{train_prefix.rstrip('/')}/{training_job_name}/train.json.gz",
            kms_key_arn=kms_key_arn,
            content_type="application/jsonlines",
        )
        test_s3_uri = upload_file_to_s3(
            s3_client,
            local_path=test_path,
            bucket_name=test_bucket_name,
            object_key=f"{test_prefix.rstrip('/')}/{training_job_name}/test.json.gz",
            kms_key_arn=kms_key_arn,
            content_type="application/jsonlines",
        )

    print(f"Submitting training job: {training_job_name}")
    training_hyperparameters = {
        "time_freq": time_freq,
        "prediction_length": str(prediction_length),
        "context_length": str(context_length),
        "epochs": str(epochs),
        "num_layers": str(num_layers),
        "num_cells": str(num_cells),
        "mini_batch_size": str(mini_batch_size),
        "likelihood": likelihood,
    }
    if feature_columns:
        training_hyperparameters["num_dynamic_feat"] = str(len(feature_columns))

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
                        "S3Uri": train_s3_uri,
                        "S3DataDistributionType": "FullyReplicated",
                    }
                },
                "ContentType": "json.gz",
                "InputMode": "File",
            },
            {
                "ChannelName": "test",
                "DataSource": {
                    "S3DataSource": {
                        "S3DataType": "S3Prefix",
                        "S3Uri": test_s3_uri,
                        "S3DataDistributionType": "FullyReplicated",
                    }
                },
                "ContentType": "json.gz",
                "InputMode": "File",
            },
        ],
        OutputDataConfig={"S3OutputPath": training_output_s3_uri},
        ResourceConfig={
            "InstanceType": args.instance_type,
            "InstanceCount": 1,
            "VolumeSizeInGB": args.volume_size_gb,
        },
        StoppingCondition={"MaxRuntimeInSeconds": args.max_runtime_seconds},
        HyperParameters=training_hyperparameters,
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

    temp_suffix = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    evaluation_model_name = build_timestamped_name(temporary_model_base_name, temp_suffix)
    evaluation_endpoint_config_name = build_timestamped_name(temporary_endpoint_cfg_base, temp_suffix)
    evaluation_endpoint_name = build_timestamped_name(temporary_endpoint_base_name, temp_suffix)

    create_temporary_evaluation_endpoint(
        sagemaker_client,
        model_name=evaluation_model_name,
        endpoint_config_name=evaluation_endpoint_config_name,
        endpoint_name=evaluation_endpoint_name,
        image_uri=inference_image_uri,
        model_data_url=model_data_url,
        role_arn=role_arn,
        instance_type=args.evaluation_instance_type,
        kms_key_arn=kms_key_arn,
    )

    try:
        wait_for_endpoint_status(sagemaker_client, evaluation_endpoint_name, args.poll_seconds)
        predicted_holdout = invoke_deepar_endpoint(
            runtime_client,
            endpoint_name=evaluation_endpoint_name,
            train_record=train_record,
            prediction_length=prediction_length,
            full_dynamic_feat=full_dynamic_feat,
        )
    finally:
        cleanup_temporary_evaluation_endpoint(
            sagemaker_client,
            model_name=evaluation_model_name,
            endpoint_config_name=evaluation_endpoint_config_name,
            endpoint_name=evaluation_endpoint_name,
            poll_seconds=args.poll_seconds,
        )

    metrics = {
        "mae": mean_absolute_error(holdout_target, predicted_holdout),
        "rmse": root_mean_squared_error(holdout_target, predicted_holdout),
        "r2": r2_score(holdout_target, predicted_holdout),
        "training_rows": len(train_target),
        "test_rows": len(holdout_target),
        "feature_columns": feature_columns,
        "dropped_constant_feature_columns": dropped_constant_feature_columns,
        "prediction_length": prediction_length,
        "context_length": context_length,
        "time_freq": time_freq,
        "forecast_algorithm": "deepar",
    }
    evaluation_s3_uri = write_evaluation_json(
        s3_client,
        model_data_url=model_data_url,
        kms_key_arn=kms_key_arn,
        metrics=metrics,
    )
    print(f"Evaluation metrics written to: {evaluation_s3_uri}")

    if args.skip_registration:
        print("Registration was skipped by request.")
        return

    model_package_arn = register_model_package(
        sagemaker_client,
        deployment_name=deployment_name,
        model_package_group_name=model_package_group_name,
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
