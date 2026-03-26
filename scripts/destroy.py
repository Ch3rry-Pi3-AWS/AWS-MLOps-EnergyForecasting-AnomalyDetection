"""Destroy helper for the AWS energy forecasting project.

This script mirrors the deployment helper and tears modules down in reverse
dependency order. The reverse ordering matters because later modules depend
on shared resources such as S3 buckets, KMS keys, and IAM roles created by
earlier modules.

Notes
-----
- The script loads a local `.env` file if one exists.
- Destroying a later module first avoids downstream references blocking the
  deletion of earlier modules.
- Full destroy removes resources in this order:

    1. SageMaker anomaly endpoint operations
    2. SageMaker model evaluation
    3. SageMaker forecast endpoint operations
    4. SageMaker anomaly endpoint configuration
    5. SageMaker forecast endpoint configuration
    6. SageMaker anomaly autoencoder training assets
    7. SageMaker anomaly One-Class SVM training assets
    8. SageMaker anomaly residual-scoring training assets
    9. SageMaker forecast TFT training assets
    10. SageMaker forecast DeepAR training assets
    11. SageMaker forecast SARIMAX training assets
    12. SageMaker anomaly training assets
    13. SageMaker forecast training assets
    14. SageMaker Studio domain
    15. SageMaker model registry
    16. Glue Silver-to-Gold scheduler
    17. Glue Silver-to-Gold job
    18. Glue Bronze-to-Silver scheduler
    19. Glue Bronze-to-Silver job
    20. Glue catalogue
    21. EventBridge Scheduler
    22. Lambda ingestion
    23. IAM foundation
    24. S3 lakehouse
    25. KMS
    26. Project context

Examples
--------
Destroy the full stack in reverse dependency order:

>>> # python scripts/destroy.py

Destroy only the Glue catalogue metadata:

>>> # python scripts/destroy.py --glue-catalog-only

Destroy only the Bronze-to-Silver scheduler:

>>> # python scripts/destroy.py --bronze-silver-scheduler-only

Destroy only the Silver-to-Gold Glue job:

>>> # python scripts/destroy.py --silver-gold-only

Destroy only the Silver-to-Gold scheduler:

>>> # python scripts/destroy.py --silver-gold-scheduler-only

Destroy only the SageMaker model registry:

>>> # python scripts/destroy.py --model-registry-only

Destroy only the SageMaker Studio domain:

>>> # python scripts/destroy.py --studio-domain-only

Destroy only the forecast-training asset stage:

>>> # python scripts/destroy.py --forecast-training-only

Destroy only the anomaly-training asset stage:

>>> # python scripts/destroy.py --anomaly-training-only

Destroy only the SARIMAX forecast-training asset stage:

>>> # python scripts/destroy.py --forecast-sarimax-training-only

Destroy only the DeepAR forecast-training asset stage:

>>> # python scripts/destroy.py --forecast-deepar-training-only

Destroy only the TFT forecast-training asset stage:

>>> # python scripts/destroy.py --forecast-tft-training-only

Destroy only the anomaly residual-scoring training asset stage:

>>> # python scripts/destroy.py --anomaly-residual-training-only

Destroy only the anomaly One-Class SVM training asset stage:

>>> # python scripts/destroy.py --anomaly-one-class-svm-training-only

Destroy only the anomaly autoencoder training asset stage:

>>> # python scripts/destroy.py --anomaly-autoencoder-training-only

Destroy only the forecast-endpoint configuration stage:

>>> # python scripts/destroy.py --forecast-endpoint-only

Destroy only the anomaly-endpoint configuration stage:

>>> # python scripts/destroy.py --anomaly-endpoint-only

Destroy only the forecast-endpoint operations stage:

>>> # python scripts/destroy.py --forecast-endpoint-ops-only

Destroy only the model-evaluation configuration stage:

>>> # python scripts/destroy.py --model-evaluation-only

Destroy only the anomaly-endpoint operations stage:

>>> # python scripts/destroy.py --anomaly-endpoint-ops-only
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


def run(cmd: list[str]) -> None:
    """
    Execute a shell command and stream its output to the terminal.

    Parameters
    ----------
    cmd : list[str]
        Command and arguments to execute.

    Examples
    --------
    >>> run(["python", "--version"])  # doctest: +SKIP
    """

    print("\n$ " + " ".join(cmd))
    subprocess.check_call(cmd)


def run_capture(cmd: list[str]) -> str:
    """
    Execute a shell command and capture its standard output.

    Parameters
    ----------
    cmd : list[str]
        Command and arguments to execute.

    Returns
    -------
    str
        Standard output captured from the command, stripped of trailing
        whitespace.

    Examples
    --------
    >>> run_capture(["python", "-c", "print('ok')"])  # doctest: +SKIP
    'ok'
    """

    print("\n$ " + " ".join(cmd))
    return subprocess.check_output(cmd, text=True).strip()


def run_capture_optional(cmd: list[str]) -> str | None:
    """
    Execute a shell command and return `None` if it fails.

    Parameters
    ----------
    cmd : list[str]
        Command and arguments to execute.

    Returns
    -------
    str | None
        Command output if successful, otherwise `None`.
    """

    try:
        return run_capture(cmd)
    except subprocess.CalledProcessError:
        return None


def load_env_file(path: Path) -> None:
    """
    Load environment variables from a simple `.env` file.

    Parameters
    ----------
    path : Path
        Path to the `.env` file.

    Notes
    -----
    Existing environment variables are preserved so that explicit shell
    configuration always takes precedence over local file values.

    Examples
    --------
    >>> from pathlib import Path
    >>> load_env_file(Path(".env"))  # doctest: +SKIP
    """

    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        value = value.strip()
        if key and key not in os.environ:
            os.environ[key] = value


def hcl_value(value: object) -> str:
    """
    Convert a Python value into a Terraform-compatible HCL literal string.

    Parameters
    ----------
    value : object
        Python value to render.

    Returns
    -------
    str
        Rendered HCL literal.

    Examples
    --------
    >>> hcl_value(False)
    'false'
    >>> hcl_value(["a", "b"])
    '["a", "b"]'
    """

    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, dict):
        inner = ", ".join(f"{key} = {hcl_value(val)}" for key, val in value.items())
        return f"{{ {inner} }}"
    if isinstance(value, (list, tuple)):
        rendered = ", ".join(hcl_value(item) for item in value)
        return f"[{rendered}]"
    escaped = str(value).replace("\"", "\\\"")
    return f"\"{escaped}\""


def write_tfvars(path: Path, items: list[tuple[str, object]]) -> None:
    """
    Write a Terraform variables file from key-value pairs.

    Parameters
    ----------
    path : Path
        Destination `terraform.tfvars` path.
    items : list[tuple[str, object]]
        Ordered key-value pairs to render into the file.
    """

    lines = [f"{key} = {hcl_value(value)}" for key, value in items]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def get_output(tf_dir: Path, output_name: str) -> str:
    """
    Read a required Terraform output from a module directory.

    Parameters
    ----------
    tf_dir : Path
        Terraform module directory.
    output_name : str
        Name of the Terraform output to retrieve.

    Returns
    -------
    str
        Output value as a string.
    """

    value = get_output_optional(tf_dir, output_name)
    if value is None:
        raise RuntimeError(f"Terraform output '{output_name}' not found in {tf_dir}.")
    return value


def get_output_optional(tf_dir: Path, output_name: str) -> str | None:
    """
    Read an optional Terraform output from CLI output or local state.

    Parameters
    ----------
    tf_dir : Path
        Terraform module directory.
    output_name : str
        Name of the Terraform output to retrieve.

    Returns
    -------
    str | None
        Output value if found, otherwise `None`.
    """

    output = run_capture_optional(["terraform", f"-chdir={tf_dir}", "output", "-raw", output_name])
    if output:
        return output
    return get_output_from_state(tf_dir, output_name)


def get_output_from_state(tf_dir: Path, output_name: str) -> str | None:
    """
    Read an output value directly from `terraform.tfstate`.

    Parameters
    ----------
    tf_dir : Path
        Terraform module directory.
    output_name : str
        Output name to look up.

    Returns
    -------
    str | None
        Output value if present, otherwise `None`.
    """

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


def tf_state_exists(tf_dir: Path) -> bool:
    """
    Check whether a module has a local Terraform state file.

    Parameters
    ----------
    tf_dir : Path
        Terraform module directory.

    Returns
    -------
    bool
        `True` if `terraform.tfstate` exists, otherwise `False`.

    Examples
    --------
    >>> from pathlib import Path
    >>> isinstance(tf_state_exists(Path(".")), bool)
    True
    """

    return (tf_dir / "terraform.tfstate").exists()


def load_context_outputs(context_dir: Path) -> dict[str, object]:
    """
    Initialise the context module and return its outputs as Python values.

    Parameters
    ----------
    context_dir : Path
        Terraform directory for `01_project_context`.

    Returns
    -------
    dict[str, object]
        Parsed context outputs, including the shared deployment name and
        standard tag dictionary.
    """

    run(["terraform", f"-chdir={context_dir}", "init"])
    return {
        "aws_region": get_output(context_dir, "aws_region"),
        "environment": get_output(context_dir, "environment"),
        "deployment_name": get_output(context_dir, "deployment_name"),
        "standard_tags": json.loads(get_output(context_dir, "standard_tags_json")),
    }


def write_kms_tfvars(kms_dir: Path, context: dict[str, object]) -> None:
    """
    Write the live variables file for the KMS module.

    Parameters
    ----------
    kms_dir : Path
        Terraform directory for `02_kms`.
    context : dict[str, object]
        Shared deployment context returned by `load_context_outputs`.
    """

    items = [
        ("aws_region", context["aws_region"]),
        ("deployment_name", context["deployment_name"]),
        ("tags", context["standard_tags"]),
    ]
    write_tfvars(kms_dir / "terraform.tfvars", items)


def write_s3_tfvars(s3_dir: Path, context: dict[str, object], kms_key_arn: str) -> None:
    """
    Write the live variables file for the S3 lakehouse module.

    Parameters
    ----------
    s3_dir : Path
        Terraform directory for `03_s3_lakehouse`.
    context : dict[str, object]
        Shared deployment context returned by `load_context_outputs`.
    kms_key_arn : str
        KMS key ARN produced by the preceding module.
    """

    items = [
        ("aws_region", context["aws_region"]),
        ("deployment_name", context["deployment_name"]),
        ("kms_key_arn", kms_key_arn),
        ("tags", context["standard_tags"]),
    ]
    write_tfvars(s3_dir / "terraform.tfvars", items)


def write_iam_tfvars(
    iam_dir: Path,
    context: dict[str, object],
    kms_key_arn: str,
    lakehouse_bucket_arn: str,
    artefact_bucket_arn: str,
    monitoring_bucket_arn: str,
) -> None:
    """
    Write the live variables file for the IAM foundation module.

    Parameters
    ----------
    iam_dir : Path
        Terraform directory for `04_iam_foundation`.
    context : dict[str, object]
        Shared deployment context returned by `load_context_outputs`.
    kms_key_arn : str
        KMS key ARN used by the execution roles.
    lakehouse_bucket_arn : str
        ARN of the main lakehouse S3 bucket.
    artefact_bucket_arn : str
        ARN of the model artefact bucket.
    monitoring_bucket_arn : str
        ARN of the monitoring bucket.
    """

    items = [
        ("aws_region", context["aws_region"]),
        ("deployment_name", context["deployment_name"]),
        ("kms_key_arn", kms_key_arn),
        ("lakehouse_bucket_arn", lakehouse_bucket_arn),
        ("artefact_bucket_arn", artefact_bucket_arn),
        ("monitoring_bucket_arn", monitoring_bucket_arn),
        ("tags", context["standard_tags"]),
    ]
    write_tfvars(iam_dir / "terraform.tfvars", items)


def write_lambda_tfvars(
    lambda_dir: Path,
    context: dict[str, object],
    kms_key_arn: str,
    lambda_role_arn: str,
    lakehouse_bucket_name: str,
) -> None:
    """
    Write the live variables file for the Lambda ingestion module.

    Parameters
    ----------
    lambda_dir : Path
        Terraform directory for `05_lambda_ingestion`.
    context : dict[str, object]
        Shared deployment context returned by `load_context_outputs`.
    kms_key_arn : str
        KMS key ARN used by the function and its outputs.
    lambda_role_arn : str
        IAM role ARN assumed by the Lambda function.
    lakehouse_bucket_name : str
        Name of the S3 lakehouse bucket receiving Bronze manifests.
    """

    items = [
        ("aws_region", context["aws_region"]),
        ("environment", context["environment"]),
        ("deployment_name", context["deployment_name"]),
        ("kms_key_arn", kms_key_arn),
        ("lambda_role_arn", lambda_role_arn),
        ("lakehouse_bucket_name", lakehouse_bucket_name),
        ("tags", context["standard_tags"]),
    ]
    write_tfvars(lambda_dir / "terraform.tfvars", items)


def write_scheduler_tfvars(
    scheduler_dir: Path,
    context: dict[str, object],
    lambda_function_name: str,
    lambda_function_arn: str,
) -> None:
    """
    Write the live variables file for the EventBridge Scheduler module.

    Parameters
    ----------
    scheduler_dir : Path
        Terraform directory for `06_eventbridge_scheduler`.
    context : dict[str, object]
        Shared deployment context returned by `load_context_outputs`.
    lambda_function_name : str
        Name of the Lambda function invoked by the schedule.
    lambda_function_arn : str
        ARN of the Lambda function invoked by the schedule.
    """

    items = [
        ("aws_region", context["aws_region"]),
        ("environment", context["environment"]),
        ("deployment_name", context["deployment_name"]),
        ("lambda_function_name", lambda_function_name),
        ("lambda_function_arn", lambda_function_arn),
        ("tags", context["standard_tags"]),
    ]
    write_tfvars(scheduler_dir / "terraform.tfvars", items)


def write_glue_catalog_tfvars(
    glue_dir: Path,
    context: dict[str, object],
    lakehouse_bucket_name: str,
) -> None:
    """
    Write the live variables file for the Glue catalogue module.

    Parameters
    ----------
    glue_dir : Path
        Terraform directory for `07_glue_catalog`.
    context : dict[str, object]
        Shared deployment context returned by `load_context_outputs`.
    lakehouse_bucket_name : str
        Name of the S3 lakehouse bucket holding Bronze raw data.
    """

    items = [
        ("aws_region", context["aws_region"]),
        ("deployment_name", context["deployment_name"]),
        ("lakehouse_bucket_name", lakehouse_bucket_name),
        ("tags", context["standard_tags"]),
    ]
    write_tfvars(glue_dir / "terraform.tfvars", items)


def write_glue_bronze_silver_tfvars(
    glue_job_dir: Path,
    context: dict[str, object],
    kms_key_arn: str,
    glue_role_arn: str,
    lakehouse_bucket_name: str,
    artefact_bucket_name: str,
    glue_database_name: str,
    energy_table_name: str,
    weather_table_name: str,
) -> None:
    """
    Write the live variables file for the Glue Bronze-to-Silver job module.

    Parameters
    ----------
    glue_job_dir : Path
        Terraform directory for `08_glue_bronze_to_silver_job`.
    context : dict[str, object]
        Shared deployment context returned by `load_context_outputs`.
    kms_key_arn : str
        KMS key ARN used to encrypt the uploaded Glue job script.
    glue_role_arn : str
        IAM role ARN assumed by the Glue job.
    lakehouse_bucket_name : str
        Name of the S3 lakehouse bucket that stores Bronze and Silver data.
    artefact_bucket_name : str
        Name of the S3 artefact bucket used for Glue scripts and temp data.
    glue_database_name : str
        Glue database name for the Bronze catalogue.
    energy_table_name : str
        Glue table name for the Bronze raw energy dataset.
    weather_table_name : str
        Glue table name for the Bronze raw weather dataset.
    """

    items = [
        ("aws_region", context["aws_region"]),
        ("deployment_name", context["deployment_name"]),
        ("kms_key_arn", kms_key_arn),
        ("glue_role_arn", glue_role_arn),
        ("lakehouse_bucket_name", lakehouse_bucket_name),
        ("artefact_bucket_name", artefact_bucket_name),
        ("glue_database_name", glue_database_name),
        ("energy_table_name", energy_table_name),
        ("weather_table_name", weather_table_name),
        ("tags", context["standard_tags"]),
    ]
    write_tfvars(glue_job_dir / "terraform.tfvars", items)


def write_glue_bronze_silver_scheduler_tfvars(
    scheduler_dir: Path,
    context: dict[str, object],
    glue_job_name: str,
    glue_job_arn: str,
) -> None:
    """
    Write the live variables file for the Bronze-to-Silver scheduler module.

    Parameters
    ----------
    scheduler_dir : Path
        Terraform directory for `09_glue_bronze_to_silver_scheduler`.
    context : dict[str, object]
        Shared deployment context returned by `load_context_outputs`.
    glue_job_name : str
        Name of the Glue job started by the scheduler.
    glue_job_arn : str
        ARN of the Glue job started by the scheduler.
    """

    items = [
        ("aws_region", context["aws_region"]),
        ("deployment_name", context["deployment_name"]),
        ("glue_job_name", glue_job_name),
        ("glue_job_arn", glue_job_arn),
        ("tags", context["standard_tags"]),
    ]
    write_tfvars(scheduler_dir / "terraform.tfvars", items)


def write_glue_silver_gold_tfvars(
    glue_job_dir: Path,
    context: dict[str, object],
    kms_key_arn: str,
    glue_role_arn: str,
    lakehouse_bucket_name: str,
    artefact_bucket_name: str,
) -> None:
    """
    Write the live variables file for the Glue Silver-to-Gold job module.

    Parameters
    ----------
    glue_job_dir : Path
        Terraform directory for `10_glue_silver_to_gold_job`.
    context : dict[str, object]
        Shared deployment context returned by `load_context_outputs`.
    kms_key_arn : str
        KMS key ARN used to encrypt the uploaded Glue job script.
    glue_role_arn : str
        IAM role ARN assumed by the Glue job.
    lakehouse_bucket_name : str
        Name of the S3 lakehouse bucket that stores Silver and Gold data.
    artefact_bucket_name : str
        Name of the S3 artefact bucket used for Glue scripts and temp data.
    """

    items = [
        ("aws_region", context["aws_region"]),
        ("deployment_name", context["deployment_name"]),
        ("kms_key_arn", kms_key_arn),
        ("glue_role_arn", glue_role_arn),
        ("lakehouse_bucket_name", lakehouse_bucket_name),
        ("artefact_bucket_name", artefact_bucket_name),
        ("tags", context["standard_tags"]),
    ]
    write_tfvars(glue_job_dir / "terraform.tfvars", items)


def write_glue_silver_gold_scheduler_tfvars(
    scheduler_dir: Path,
    context: dict[str, object],
    glue_job_name: str,
    glue_job_arn: str,
) -> None:
    """
    Write the live variables file for the Silver-to-Gold scheduler module.

    Parameters
    ----------
    scheduler_dir : Path
        Terraform directory for `11_glue_silver_to_gold_scheduler`.
    context : dict[str, object]
        Shared deployment context returned by `load_context_outputs`.
    glue_job_name : str
        Name of the Glue job started by the scheduler.
    glue_job_arn : str
        ARN of the Glue job started by the scheduler.
    """

    items = [
        ("aws_region", context["aws_region"]),
        ("deployment_name", context["deployment_name"]),
        ("glue_job_name", glue_job_name),
        ("glue_job_arn", glue_job_arn),
        ("tags", context["standard_tags"]),
    ]
    write_tfvars(scheduler_dir / "terraform.tfvars", items)


def write_model_registry_tfvars(
    registry_dir: Path,
    context: dict[str, object],
) -> None:
    """
    Write the live variables file for the SageMaker model registry module.

    Parameters
    ----------
    registry_dir : Path
        Terraform directory for `12_sagemaker_model_registry`.
    context : dict[str, object]
        Shared deployment context returned by `load_context_outputs`.
    """

    items = [
        ("aws_region", context["aws_region"]),
        ("deployment_name", context["deployment_name"]),
        ("tags", context["standard_tags"]),
    ]
    write_tfvars(registry_dir / "terraform.tfvars", items)


def write_studio_domain_tfvars(
    studio_dir: Path,
    context: dict[str, object],
    kms_key_arn: str,
    sagemaker_role_arn: str,
) -> None:
    """
    Write the live variables file for the SageMaker Studio domain module.

    Parameters
    ----------
    studio_dir : Path
        Terraform directory for `13_sagemaker_studio_domain`.
    context : dict[str, object]
        Shared deployment context returned by `load_context_outputs`.
    kms_key_arn : str
        KMS key ARN used by the Studio domain for encrypted storage.
    sagemaker_role_arn : str
        IAM role ARN assumed by SageMaker Studio users.
    """

    items = [
        ("aws_region", context["aws_region"]),
        ("deployment_name", context["deployment_name"]),
        ("kms_key_arn", kms_key_arn),
        ("sagemaker_role_arn", sagemaker_role_arn),
        ("tags", context["standard_tags"]),
    ]
    write_tfvars(studio_dir / "terraform.tfvars", items)


def write_forecast_training_tfvars(
    training_dir: Path,
    context: dict[str, object],
    kms_key_arn: str,
    artefact_bucket_name: str,
    lakehouse_bucket_name: str,
    sagemaker_role_arn: str,
    forecast_model_package_group_name: str,
) -> None:
    """
    Write the live variables file for the forecast-training asset module.

    Parameters
    ----------
    training_dir : Path
        Terraform directory for `14_sagemaker_forecast_training`.
    context : dict[str, object]
        Shared deployment context returned by `load_context_outputs`.
    kms_key_arn : str
        KMS key ARN used to encrypt the uploaded source bundle.
    artefact_bucket_name : str
        Name of the S3 artefact bucket used for training code and outputs.
    lakehouse_bucket_name : str
        Name of the S3 lakehouse bucket containing Gold forecast features.
    sagemaker_role_arn : str
        IAM role ARN assumed by the SageMaker training job.
    forecast_model_package_group_name : str
        Name of the forecast model package group used for registration.
    """

    items = [
        ("aws_region", context["aws_region"]),
        ("deployment_name", context["deployment_name"]),
        ("kms_key_arn", kms_key_arn),
        ("artefact_bucket_name", artefact_bucket_name),
        ("lakehouse_bucket_name", lakehouse_bucket_name),
        ("sagemaker_role_arn", sagemaker_role_arn),
        ("forecast_model_package_group_name", forecast_model_package_group_name),
    ]
    write_tfvars(training_dir / "terraform.tfvars", items)


def write_anomaly_training_tfvars(
    training_dir: Path,
    context: dict[str, object],
    kms_key_arn: str,
    artefact_bucket_name: str,
    lakehouse_bucket_name: str,
    sagemaker_role_arn: str,
    anomaly_model_package_group_name: str,
) -> None:
    """
    Write the live variables file for the anomaly-training asset module.

    Parameters
    ----------
    training_dir : Path
        Terraform directory for `15_sagemaker_anomaly_training`.
    context : dict[str, object]
        Shared deployment context returned by `load_context_outputs`.
    kms_key_arn : str
        KMS key ARN used to encrypt the uploaded source bundle.
    artefact_bucket_name : str
        Name of the S3 artefact bucket used for training code and outputs.
    lakehouse_bucket_name : str
        Name of the S3 lakehouse bucket containing Gold anomaly features.
    sagemaker_role_arn : str
        IAM role ARN assumed by the SageMaker training job.
    anomaly_model_package_group_name : str
        Name of the anomaly model package group used for registration.
    """

    items = [
        ("aws_region", context["aws_region"]),
        ("deployment_name", context["deployment_name"]),
        ("kms_key_arn", kms_key_arn),
        ("artefact_bucket_name", artefact_bucket_name),
        ("lakehouse_bucket_name", lakehouse_bucket_name),
        ("sagemaker_role_arn", sagemaker_role_arn),
        ("anomaly_model_package_group_name", anomaly_model_package_group_name),
    ]
    write_tfvars(training_dir / "terraform.tfvars", items)


def write_forecast_sarimax_training_tfvars(
    training_dir: Path,
    context: dict[str, object],
    kms_key_arn: str,
    artefact_bucket_name: str,
    lakehouse_bucket_name: str,
    sagemaker_role_arn: str,
    forecast_model_package_group_name: str,
) -> None:
    """
    Write the live variables file for the SARIMAX forecast-training asset module.

    Parameters
    ----------
    training_dir : Path
        Terraform directory for `21_sagemaker_forecast_sarimax_training`.
    context : dict[str, object]
        Shared deployment context returned by `load_context_outputs`.
    kms_key_arn : str
        KMS key ARN used to encrypt the uploaded source bundle.
    artefact_bucket_name : str
        Name of the S3 artefact bucket used for training code and outputs.
    lakehouse_bucket_name : str
        Name of the S3 lakehouse bucket containing Gold forecast features.
    sagemaker_role_arn : str
        IAM role ARN assumed by the SageMaker training job.
    forecast_model_package_group_name : str
        Name of the forecast model package group used for registration.
    """

    items = [
        ("aws_region", context["aws_region"]),
        ("deployment_name", context["deployment_name"]),
        ("kms_key_arn", kms_key_arn),
        ("artefact_bucket_name", artefact_bucket_name),
        ("lakehouse_bucket_name", lakehouse_bucket_name),
        ("sagemaker_role_arn", sagemaker_role_arn),
        ("forecast_model_package_group_name", forecast_model_package_group_name),
    ]
    write_tfvars(training_dir / "terraform.tfvars", items)


def write_forecast_deepar_training_tfvars(
    training_dir: Path,
    context: dict[str, object],
    kms_key_arn: str,
    artefact_bucket_name: str,
    lakehouse_bucket_name: str,
    sagemaker_role_arn: str,
    forecast_model_package_group_name: str,
) -> None:
    """
    Write the live variables file for the DeepAR forecast-training asset module.

    Parameters
    ----------
    training_dir : Path
        Terraform directory for `22_sagemaker_forecast_deepar_training`.
    context : dict[str, object]
        Shared deployment context returned by `load_context_outputs`.
    kms_key_arn : str
        KMS key ARN used to encrypt the staged DeepAR inputs and outputs.
    artefact_bucket_name : str
        Name of the S3 artefact bucket used for training data preparation and outputs.
    lakehouse_bucket_name : str
        Name of the S3 lakehouse bucket containing Gold forecast features.
    sagemaker_role_arn : str
        IAM role ARN assumed by the SageMaker training job.
    forecast_model_package_group_name : str
        Name of the forecast model package group used for registration.
    """

    items = [
        ("aws_region", context["aws_region"]),
        ("deployment_name", context["deployment_name"]),
        ("kms_key_arn", kms_key_arn),
        ("artefact_bucket_name", artefact_bucket_name),
        ("lakehouse_bucket_name", lakehouse_bucket_name),
        ("sagemaker_role_arn", sagemaker_role_arn),
        ("forecast_model_package_group_name", forecast_model_package_group_name),
    ]
    write_tfvars(training_dir / "terraform.tfvars", items)


def write_forecast_tft_training_tfvars(
    training_dir: Path,
    context: dict[str, object],
    kms_key_arn: str,
    artefact_bucket_name: str,
    lakehouse_bucket_name: str,
    sagemaker_role_arn: str,
    forecast_model_package_group_name: str,
) -> None:
    """
    Write the live variables file for the TFT forecast-training asset module.

    Parameters
    ----------
    training_dir : Path
        Terraform directory for `23_sagemaker_forecast_tft_training`.
    context : dict[str, object]
        Shared deployment context returned by `load_context_outputs`.
    kms_key_arn : str
        KMS key ARN used to encrypt the uploaded TFT source bundle and outputs.
    artefact_bucket_name : str
        Name of the S3 artefact bucket used for training code and outputs.
    lakehouse_bucket_name : str
        Name of the S3 lakehouse bucket containing Gold forecast features.
    sagemaker_role_arn : str
        IAM role ARN assumed by the SageMaker training job.
    forecast_model_package_group_name : str
        Name of the forecast model package group used for registration.
    """

    items = [
        ("aws_region", context["aws_region"]),
        ("deployment_name", context["deployment_name"]),
        ("kms_key_arn", kms_key_arn),
        ("artefact_bucket_name", artefact_bucket_name),
        ("lakehouse_bucket_name", lakehouse_bucket_name),
        ("sagemaker_role_arn", sagemaker_role_arn),
        ("forecast_model_package_group_name", forecast_model_package_group_name),
    ]
    write_tfvars(training_dir / "terraform.tfvars", items)


def write_anomaly_residual_training_tfvars(
    training_dir: Path,
    context: dict[str, object],
    kms_key_arn: str,
    artefact_bucket_name: str,
    lakehouse_bucket_name: str,
    sagemaker_role_arn: str,
    anomaly_model_package_group_name: str,
) -> None:
    """
    Write the live variables file for the anomaly residual-training asset module.

    Parameters
    ----------
    training_dir : Path
        Terraform directory for `24_sagemaker_anomaly_residual_training`.
    context : dict[str, object]
        Shared deployment context returned by `load_context_outputs`.
    kms_key_arn : str
        KMS key ARN used to encrypt the uploaded source bundle and outputs.
    artefact_bucket_name : str
        Name of the S3 artefact bucket used for training code and outputs.
    lakehouse_bucket_name : str
        Name of the S3 lakehouse bucket containing Gold anomaly features.
    sagemaker_role_arn : str
        IAM role ARN assumed by the SageMaker training job.
    anomaly_model_package_group_name : str
        Name of the anomaly model package group used for registration.
    """

    items = [
        ("aws_region", context["aws_region"]),
        ("deployment_name", context["deployment_name"]),
        ("kms_key_arn", kms_key_arn),
        ("artefact_bucket_name", artefact_bucket_name),
        ("lakehouse_bucket_name", lakehouse_bucket_name),
        ("sagemaker_role_arn", sagemaker_role_arn),
        ("anomaly_model_package_group_name", anomaly_model_package_group_name),
    ]
    write_tfvars(training_dir / "terraform.tfvars", items)


def write_anomaly_one_class_svm_training_tfvars(
    training_dir: Path,
    context: dict[str, object],
    kms_key_arn: str,
    artefact_bucket_name: str,
    lakehouse_bucket_name: str,
    sagemaker_role_arn: str,
    anomaly_model_package_group_name: str,
) -> None:
    """
    Write the live variables file for the anomaly One-Class SVM asset module.

    Parameters
    ----------
    training_dir : Path
        Terraform directory for `25_sagemaker_anomaly_one_class_svm_training`.
    context : dict[str, object]
        Shared deployment context returned by `load_context_outputs`.
    kms_key_arn : str
        KMS key ARN used to encrypt the uploaded source bundle and outputs.
    artefact_bucket_name : str
        Name of the S3 artefact bucket used for training code and outputs.
    lakehouse_bucket_name : str
        Name of the S3 lakehouse bucket containing Gold anomaly features.
    sagemaker_role_arn : str
        IAM role ARN assumed by the SageMaker training job.
    anomaly_model_package_group_name : str
        Name of the anomaly model package group used for registration.
    """

    items = [
        ("aws_region", context["aws_region"]),
        ("deployment_name", context["deployment_name"]),
        ("kms_key_arn", kms_key_arn),
        ("artefact_bucket_name", artefact_bucket_name),
        ("lakehouse_bucket_name", lakehouse_bucket_name),
        ("sagemaker_role_arn", sagemaker_role_arn),
        ("anomaly_model_package_group_name", anomaly_model_package_group_name),
    ]
    write_tfvars(training_dir / "terraform.tfvars", items)


def write_anomaly_autoencoder_training_tfvars(
    training_dir: Path,
    context: dict[str, object],
    kms_key_arn: str,
    artefact_bucket_name: str,
    lakehouse_bucket_name: str,
    sagemaker_role_arn: str,
    anomaly_model_package_group_name: str,
) -> None:
    """
    Write the live variables file for the anomaly autoencoder asset module.

    Parameters
    ----------
    training_dir : Path
        Terraform directory for `26_sagemaker_anomaly_autoencoder_training`.
    context : dict[str, object]
        Shared deployment context returned by `load_context_outputs`.
    kms_key_arn : str
        KMS key ARN used to encrypt the uploaded source bundle and outputs.
    artefact_bucket_name : str
        Name of the S3 artefact bucket used for training code and outputs.
    lakehouse_bucket_name : str
        Name of the S3 lakehouse bucket containing Gold anomaly features.
    sagemaker_role_arn : str
        IAM role ARN assumed by the SageMaker training job.
    anomaly_model_package_group_name : str
        Name of the anomaly model package group used for registration.
    """

    items = [
        ("aws_region", context["aws_region"]),
        ("deployment_name", context["deployment_name"]),
        ("kms_key_arn", kms_key_arn),
        ("artefact_bucket_name", artefact_bucket_name),
        ("lakehouse_bucket_name", lakehouse_bucket_name),
        ("sagemaker_role_arn", sagemaker_role_arn),
        ("anomaly_model_package_group_name", anomaly_model_package_group_name),
    ]
    write_tfvars(training_dir / "terraform.tfvars", items)


def write_forecast_endpoint_tfvars(
    endpoint_dir: Path,
    context: dict[str, object],
    kms_key_arn: str,
    sagemaker_role_arn: str,
    forecast_model_package_group_name: str,
) -> None:
    """
    Write the live variables file for the forecast-endpoint configuration module.

    Parameters
    ----------
    endpoint_dir : Path
        Terraform directory for `16_sagemaker_forecast_endpoint`.
    context : dict[str, object]
        Shared deployment context returned by `load_context_outputs`.
    kms_key_arn : str
        KMS key ARN used to encrypt endpoint resources.
    sagemaker_role_arn : str
        IAM role ARN assumed by SageMaker models and endpoints.
    forecast_model_package_group_name : str
        Name of the forecast model package group used for deployment lookups.
    """

    items = [
        ("aws_region", context["aws_region"]),
        ("deployment_name", context["deployment_name"]),
        ("kms_key_arn", kms_key_arn),
        ("sagemaker_role_arn", sagemaker_role_arn),
        ("forecast_model_package_group_name", forecast_model_package_group_name),
    ]
    write_tfvars(endpoint_dir / "terraform.tfvars", items)


def write_anomaly_endpoint_tfvars(
    endpoint_dir: Path,
    context: dict[str, object],
    kms_key_arn: str,
    sagemaker_role_arn: str,
    anomaly_model_package_group_name: str,
) -> None:
    """
    Write the live variables file for the anomaly-endpoint configuration module.

    Parameters
    ----------
    endpoint_dir : Path
        Terraform directory for `17_sagemaker_anomaly_endpoint`.
    context : dict[str, object]
        Shared deployment context returned by `load_context_outputs`.
    kms_key_arn : str
        KMS key ARN used to encrypt endpoint resources.
    sagemaker_role_arn : str
        IAM role ARN assumed by SageMaker models and endpoints.
    anomaly_model_package_group_name : str
        Name of the anomaly model package group used for deployment lookups.
    """

    items = [
        ("aws_region", context["aws_region"]),
        ("deployment_name", context["deployment_name"]),
        ("kms_key_arn", kms_key_arn),
        ("sagemaker_role_arn", sagemaker_role_arn),
        ("anomaly_model_package_group_name", anomaly_model_package_group_name),
    ]
    write_tfvars(endpoint_dir / "terraform.tfvars", items)


def write_forecast_endpoint_ops_tfvars(
    ops_dir: Path,
    context: dict[str, object],
    forecast_endpoint_name: str,
    forecast_endpoint_variant_name: str,
) -> None:
    """
    Write the live variables file for the forecast-endpoint operations module.

    Parameters
    ----------
    ops_dir : Path
        Terraform directory for `18_sagemaker_forecast_endpoint_ops`.
    context : dict[str, object]
        Shared deployment context returned by `load_context_outputs`.
    forecast_endpoint_name : str
        Stable forecast endpoint name created by the endpoint deployment runner.
    forecast_endpoint_variant_name : str
        Production variant name exposed by the forecast-endpoint configuration stage.
    """

    items = [
        ("aws_region", context["aws_region"]),
        ("deployment_name", context["deployment_name"]),
        ("forecast_endpoint_name", forecast_endpoint_name),
        ("forecast_endpoint_variant_name", forecast_endpoint_variant_name),
    ]
    write_tfvars(ops_dir / "terraform.tfvars", items)


def write_anomaly_endpoint_ops_tfvars(
    ops_dir: Path,
    context: dict[str, object],
    anomaly_endpoint_name: str,
    anomaly_endpoint_variant_name: str,
) -> None:
    """
    Write the live variables file for the anomaly-endpoint operations module.

    Parameters
    ----------
    ops_dir : Path
        Terraform directory for `20_sagemaker_anomaly_endpoint_ops`.
    context : dict[str, object]
        Shared deployment context returned by `load_context_outputs`.
    anomaly_endpoint_name : str
        Stable anomaly endpoint name created by the endpoint deployment runner.
    anomaly_endpoint_variant_name : str
        Production variant name exposed by the anomaly-endpoint configuration stage.
    """

    items = [
        ("aws_region", context["aws_region"]),
        ("deployment_name", context["deployment_name"]),
        ("anomaly_endpoint_name", anomaly_endpoint_name),
        ("anomaly_endpoint_variant_name", anomaly_endpoint_variant_name),
    ]
    write_tfvars(ops_dir / "terraform.tfvars", items)


def write_model_evaluation_tfvars(
    evaluation_dir: Path,
    context: dict[str, object],
    kms_key_arn: str,
    artefact_bucket_name: str,
    forecast_model_package_group_name: str,
    anomaly_model_package_group_name: str,
) -> None:
    """
    Write the live variables file for the SageMaker model-evaluation module.

    Parameters
    ----------
    evaluation_dir : Path
        Terraform directory for `19_sagemaker_model_evaluation`.
    context : dict[str, object]
        Shared deployment context returned by `load_context_outputs`.
    kms_key_arn : str
        KMS key ARN used to encrypt uploaded evaluation reports.
    artefact_bucket_name : str
        Artefact bucket name used to store evaluation reports.
    forecast_model_package_group_name : str
        Forecast model package group name consumed by the evaluation runner.
    anomaly_model_package_group_name : str
        Anomaly model package group name consumed by the evaluation runner.
    """

    items = [
        ("aws_region", context["aws_region"]),
        ("deployment_name", context["deployment_name"]),
        ("artefact_bucket_name", artefact_bucket_name),
        ("kms_key_arn", kms_key_arn),
        ("forecast_model_package_group_name", forecast_model_package_group_name),
        ("anomaly_model_package_group_name", anomaly_model_package_group_name),
    ]
    write_tfvars(evaluation_dir / "terraform.tfvars", items)


def destroy_stack(tf_dir: Path) -> None:
    """
    Destroy a Terraform module.

    Parameters
    ----------
    tf_dir : Path
        Terraform module directory.
    """

    run(["terraform", f"-chdir={tf_dir}", "destroy", "-auto-approve"])


def destroy_stack_if_state(tf_dir: Path) -> bool:
    """
    Destroy a Terraform module only if local state exists.

    Parameters
    ----------
    tf_dir : Path
        Terraform module directory.

    Returns
    -------
    bool
        `True` if a destroy was attempted, otherwise `False`.
    """

    if not tf_state_exists(tf_dir):
        return False
    destroy_stack(tf_dir)
    return True


if __name__ == "__main__":
    try:
        parser = argparse.ArgumentParser(
            description="Destroy Terraform stacks for the AWS energy forecasting foundation layer."
        )
        group = parser.add_mutually_exclusive_group()
        group.add_argument("--context-only", action="store_true", help="Destroy only the project context")
        group.add_argument("--kms-only", action="store_true", help="Destroy only the KMS stack")
        group.add_argument("--s3-only", action="store_true", help="Destroy only the S3 lakehouse stack")
        group.add_argument("--iam-only", action="store_true", help="Destroy only the IAM foundation stack")
        group.add_argument("--lambda-only", action="store_true", help="Destroy only the ingestion Lambda stack")
        group.add_argument("--scheduler-only", action="store_true", help="Destroy only the EventBridge Scheduler stack")
        group.add_argument("--glue-catalog-only", action="store_true", help="Destroy only the Glue catalogue stack")
        group.add_argument("--bronze-silver-only", action="store_true", help="Destroy only the Glue Bronze-to-Silver job")
        group.add_argument(
            "--bronze-silver-scheduler-only",
            action="store_true",
            help="Destroy only the Bronze-to-Silver scheduler stack",
        )
        group.add_argument("--silver-gold-only", action="store_true", help="Destroy only the Glue Silver-to-Gold job")
        group.add_argument(
            "--silver-gold-scheduler-only",
            action="store_true",
            help="Destroy only the Silver-to-Gold scheduler stack",
        )
        group.add_argument("--model-registry-only", action="store_true", help="Destroy only the SageMaker model registry stack")
        group.add_argument("--studio-domain-only", action="store_true", help="Destroy only the SageMaker Studio domain stack")
        group.add_argument("--forecast-training-only", action="store_true", help="Destroy only the SageMaker forecast training asset stack")
        group.add_argument("--anomaly-training-only", action="store_true", help="Destroy only the SageMaker anomaly training asset stack")
        group.add_argument("--forecast-sarimax-training-only", action="store_true", help="Destroy only the SageMaker forecast SARIMAX training asset stack")
        group.add_argument("--forecast-deepar-training-only", action="store_true", help="Destroy only the SageMaker forecast DeepAR training asset stack")
        group.add_argument("--forecast-tft-training-only", action="store_true", help="Destroy only the SageMaker forecast TFT training asset stack")
        group.add_argument("--anomaly-residual-training-only", action="store_true", help="Destroy only the SageMaker anomaly residual-scoring training asset stack")
        group.add_argument("--anomaly-one-class-svm-training-only", action="store_true", help="Destroy only the SageMaker anomaly One-Class SVM training asset stack")
        group.add_argument("--anomaly-autoencoder-training-only", action="store_true", help="Destroy only the SageMaker anomaly autoencoder training asset stack")
        group.add_argument("--forecast-endpoint-only", action="store_true", help="Destroy only the SageMaker forecast endpoint configuration stack")
        group.add_argument("--anomaly-endpoint-only", action="store_true", help="Destroy only the SageMaker anomaly endpoint configuration stack")
        group.add_argument("--forecast-endpoint-ops-only", action="store_true", help="Destroy only the SageMaker forecast endpoint monitoring and autoscaling stack")
        group.add_argument("--model-evaluation-only", action="store_true", help="Destroy only the SageMaker model-evaluation configuration stack")
        group.add_argument("--anomaly-endpoint-ops-only", action="store_true", help="Destroy only the SageMaker anomaly endpoint monitoring and autoscaling stack")
        args = parser.parse_args()

        repo_root = Path(__file__).resolve().parent.parent
        load_env_file(repo_root / ".env")

        context_dir = repo_root / "terraform" / "01_project_context"
        kms_dir = repo_root / "terraform" / "02_kms"
        s3_dir = repo_root / "terraform" / "03_s3_lakehouse"
        iam_dir = repo_root / "terraform" / "04_iam_foundation"
        lambda_dir = repo_root / "terraform" / "05_lambda_ingestion"
        scheduler_dir = repo_root / "terraform" / "06_eventbridge_scheduler"
        glue_catalog_dir = repo_root / "terraform" / "07_glue_catalog"
        glue_bronze_silver_dir = repo_root / "terraform" / "08_glue_bronze_to_silver_job"
        glue_bronze_silver_scheduler_dir = repo_root / "terraform" / "09_glue_bronze_to_silver_scheduler"
        glue_silver_gold_dir = repo_root / "terraform" / "10_glue_silver_to_gold_job"
        glue_silver_gold_scheduler_dir = repo_root / "terraform" / "11_glue_silver_to_gold_scheduler"
        model_registry_dir = repo_root / "terraform" / "12_sagemaker_model_registry"
        studio_domain_dir = repo_root / "terraform" / "13_sagemaker_studio_domain"
        forecast_training_dir = repo_root / "terraform" / "14_sagemaker_forecast_training"
        anomaly_training_dir = repo_root / "terraform" / "15_sagemaker_anomaly_training"
        forecast_endpoint_dir = repo_root / "terraform" / "16_sagemaker_forecast_endpoint"
        anomaly_endpoint_dir = repo_root / "terraform" / "17_sagemaker_anomaly_endpoint"
        forecast_endpoint_ops_dir = repo_root / "terraform" / "18_sagemaker_forecast_endpoint_ops"
        model_evaluation_dir = repo_root / "terraform" / "19_sagemaker_model_evaluation"
        anomaly_endpoint_ops_dir = repo_root / "terraform" / "20_sagemaker_anomaly_endpoint_ops"
        forecast_sarimax_training_dir = repo_root / "terraform" / "21_sagemaker_forecast_sarimax_training"
        forecast_deepar_training_dir = repo_root / "terraform" / "22_sagemaker_forecast_deepar_training"
        forecast_tft_training_dir = repo_root / "terraform" / "23_sagemaker_forecast_tft_training"
        anomaly_residual_training_dir = repo_root / "terraform" / "24_sagemaker_anomaly_residual_training"
        anomaly_one_class_svm_training_dir = repo_root / "terraform" / "25_sagemaker_anomaly_one_class_svm_training"
        anomaly_autoencoder_training_dir = repo_root / "terraform" / "26_sagemaker_anomaly_autoencoder_training"

        if args.context_only:
            destroy_stack_if_state(context_dir)
            sys.exit(0)

        if args.kms_only:
            context = load_context_outputs(context_dir)
            write_kms_tfvars(kms_dir, context)
            destroy_stack_if_state(kms_dir)
            sys.exit(0)

        if args.s3_only:
            context = load_context_outputs(context_dir)
            run(["terraform", f"-chdir={kms_dir}", "init"])
            kms_key_arn = get_output(kms_dir, "kms_key_arn")
            write_s3_tfvars(s3_dir, context, kms_key_arn)
            destroy_stack_if_state(s3_dir)
            sys.exit(0)

        if args.iam_only:
            context = load_context_outputs(context_dir)
            run(["terraform", f"-chdir={kms_dir}", "init"])
            run(["terraform", f"-chdir={s3_dir}", "init"])
            kms_key_arn = get_output(kms_dir, "kms_key_arn")
            lakehouse_bucket_arn = get_output(s3_dir, "lakehouse_bucket_arn")
            artefact_bucket_arn = get_output(s3_dir, "artefact_bucket_arn")
            monitoring_bucket_arn = get_output(s3_dir, "monitoring_bucket_arn")
            write_iam_tfvars(
                iam_dir,
                context,
                kms_key_arn,
                lakehouse_bucket_arn,
                artefact_bucket_arn,
                monitoring_bucket_arn,
            )
            destroy_stack_if_state(iam_dir)
            sys.exit(0)

        if args.lambda_only:
            context = load_context_outputs(context_dir)
            run(["terraform", f"-chdir={kms_dir}", "init"])
            run(["terraform", f"-chdir={s3_dir}", "init"])
            run(["terraform", f"-chdir={iam_dir}", "init"])
            kms_key_arn = get_output(kms_dir, "kms_key_arn")
            lambda_role_arn = get_output(iam_dir, "lambda_role_arn")
            lakehouse_bucket_name = get_output(s3_dir, "lakehouse_bucket_name")
            write_lambda_tfvars(
                lambda_dir,
                context,
                kms_key_arn,
                lambda_role_arn,
                lakehouse_bucket_name,
            )
            destroy_stack_if_state(lambda_dir)
            sys.exit(0)

        if args.scheduler_only:
            context = load_context_outputs(context_dir)
            run(["terraform", f"-chdir={lambda_dir}", "init"])
            lambda_function_name = get_output(lambda_dir, "lambda_function_name")
            lambda_function_arn = get_output(lambda_dir, "lambda_function_arn")
            write_scheduler_tfvars(
                scheduler_dir,
                context,
                lambda_function_name,
                lambda_function_arn,
            )
            destroy_stack_if_state(scheduler_dir)
            sys.exit(0)

        if args.glue_catalog_only:
            context = load_context_outputs(context_dir)
            run(["terraform", f"-chdir={s3_dir}", "init"])
            lakehouse_bucket_name = get_output(s3_dir, "lakehouse_bucket_name")
            write_glue_catalog_tfvars(
                glue_catalog_dir,
                context,
                lakehouse_bucket_name,
            )
            destroy_stack_if_state(glue_catalog_dir)
            sys.exit(0)

        if args.bronze_silver_only:
            context = load_context_outputs(context_dir)
            run(["terraform", f"-chdir={kms_dir}", "init"])
            run(["terraform", f"-chdir={s3_dir}", "init"])
            run(["terraform", f"-chdir={iam_dir}", "init"])
            run(["terraform", f"-chdir={glue_catalog_dir}", "init"])
            kms_key_arn = get_output(kms_dir, "kms_key_arn")
            glue_role_arn = get_output(iam_dir, "glue_role_arn")
            lakehouse_bucket_name = get_output(s3_dir, "lakehouse_bucket_name")
            artefact_bucket_name = get_output(s3_dir, "artefact_bucket_name")
            glue_database_name = get_output(glue_catalog_dir, "glue_database_name")
            energy_table_name = get_output(glue_catalog_dir, "energy_table_name")
            weather_table_name = get_output(glue_catalog_dir, "weather_table_name")
            write_glue_bronze_silver_tfvars(
                glue_bronze_silver_dir,
                context,
                kms_key_arn,
                glue_role_arn,
                lakehouse_bucket_name,
                artefact_bucket_name,
                glue_database_name,
                energy_table_name,
                weather_table_name,
            )
            destroy_stack_if_state(glue_bronze_silver_dir)
            sys.exit(0)

        if args.bronze_silver_scheduler_only:
            context = load_context_outputs(context_dir)
            run(["terraform", f"-chdir={glue_bronze_silver_dir}", "init"])
            glue_job_name = get_output(glue_bronze_silver_dir, "glue_job_name")
            glue_job_arn = get_output(glue_bronze_silver_dir, "glue_job_arn")
            write_glue_bronze_silver_scheduler_tfvars(
                glue_bronze_silver_scheduler_dir,
                context,
                glue_job_name,
                glue_job_arn,
            )
            destroy_stack_if_state(glue_bronze_silver_scheduler_dir)
            sys.exit(0)

        if args.silver_gold_only:
            context = load_context_outputs(context_dir)
            run(["terraform", f"-chdir={kms_dir}", "init"])
            run(["terraform", f"-chdir={s3_dir}", "init"])
            run(["terraform", f"-chdir={iam_dir}", "init"])
            kms_key_arn = get_output(kms_dir, "kms_key_arn")
            glue_role_arn = get_output(iam_dir, "glue_role_arn")
            lakehouse_bucket_name = get_output(s3_dir, "lakehouse_bucket_name")
            artefact_bucket_name = get_output(s3_dir, "artefact_bucket_name")
            write_glue_silver_gold_tfvars(
                glue_silver_gold_dir,
                context,
                kms_key_arn,
                glue_role_arn,
                lakehouse_bucket_name,
                artefact_bucket_name,
            )
            destroy_stack_if_state(glue_silver_gold_dir)
            sys.exit(0)

        if args.silver_gold_scheduler_only:
            context = load_context_outputs(context_dir)
            run(["terraform", f"-chdir={glue_silver_gold_dir}", "init"])
            glue_job_name = get_output(glue_silver_gold_dir, "glue_job_name")
            glue_job_arn = get_output(glue_silver_gold_dir, "glue_job_arn")
            write_glue_silver_gold_scheduler_tfvars(
                glue_silver_gold_scheduler_dir,
                context,
                glue_job_name,
                glue_job_arn,
            )
            destroy_stack_if_state(glue_silver_gold_scheduler_dir)
            sys.exit(0)

        if args.model_registry_only:
            context = load_context_outputs(context_dir)
            write_model_registry_tfvars(model_registry_dir, context)
            destroy_stack_if_state(model_registry_dir)
            sys.exit(0)

        if args.studio_domain_only:
            context = load_context_outputs(context_dir)
            run(["terraform", f"-chdir={kms_dir}", "init"])
            run(["terraform", f"-chdir={iam_dir}", "init"])
            kms_key_arn = get_output(kms_dir, "kms_key_arn")
            sagemaker_role_arn = get_output(iam_dir, "sagemaker_role_arn")
            write_studio_domain_tfvars(
                studio_domain_dir,
                context,
                kms_key_arn,
                sagemaker_role_arn,
            )
            destroy_stack_if_state(studio_domain_dir)
            sys.exit(0)

        if args.forecast_training_only:
            context = load_context_outputs(context_dir)
            run(["terraform", f"-chdir={kms_dir}", "init"])
            run(["terraform", f"-chdir={s3_dir}", "init"])
            run(["terraform", f"-chdir={iam_dir}", "init"])
            run(["terraform", f"-chdir={model_registry_dir}", "init"])
            kms_key_arn = get_output(kms_dir, "kms_key_arn")
            artefact_bucket_name = get_output(s3_dir, "artefact_bucket_name")
            lakehouse_bucket_name = get_output(s3_dir, "lakehouse_bucket_name")
            sagemaker_role_arn = get_output(iam_dir, "sagemaker_role_arn")
            forecast_model_package_group_name = get_output(model_registry_dir, "forecast_model_package_group_name")
            write_forecast_training_tfvars(
                forecast_training_dir,
                context,
                kms_key_arn,
                artefact_bucket_name,
                lakehouse_bucket_name,
                sagemaker_role_arn,
                forecast_model_package_group_name,
            )
            destroy_stack_if_state(forecast_training_dir)
            sys.exit(0)

        if args.anomaly_training_only:
            context = load_context_outputs(context_dir)
            run(["terraform", f"-chdir={kms_dir}", "init"])
            run(["terraform", f"-chdir={s3_dir}", "init"])
            run(["terraform", f"-chdir={iam_dir}", "init"])
            run(["terraform", f"-chdir={model_registry_dir}", "init"])
            kms_key_arn = get_output(kms_dir, "kms_key_arn")
            artefact_bucket_name = get_output(s3_dir, "artefact_bucket_name")
            lakehouse_bucket_name = get_output(s3_dir, "lakehouse_bucket_name")
            sagemaker_role_arn = get_output(iam_dir, "sagemaker_role_arn")
            anomaly_model_package_group_name = get_output(model_registry_dir, "anomaly_model_package_group_name")
            write_anomaly_training_tfvars(
                anomaly_training_dir,
                context,
                kms_key_arn,
                artefact_bucket_name,
                lakehouse_bucket_name,
                sagemaker_role_arn,
                anomaly_model_package_group_name,
            )
            destroy_stack_if_state(anomaly_training_dir)
            sys.exit(0)

        if args.forecast_sarimax_training_only:
            context = load_context_outputs(context_dir)
            run(["terraform", f"-chdir={kms_dir}", "init"])
            run(["terraform", f"-chdir={s3_dir}", "init"])
            run(["terraform", f"-chdir={iam_dir}", "init"])
            run(["terraform", f"-chdir={model_registry_dir}", "init"])
            kms_key_arn = get_output(kms_dir, "kms_key_arn")
            artefact_bucket_name = get_output(s3_dir, "artefact_bucket_name")
            lakehouse_bucket_name = get_output(s3_dir, "lakehouse_bucket_name")
            sagemaker_role_arn = get_output(iam_dir, "sagemaker_role_arn")
            forecast_model_package_group_name = get_output(model_registry_dir, "forecast_model_package_group_name")
            write_forecast_sarimax_training_tfvars(
                forecast_sarimax_training_dir,
                context,
                kms_key_arn,
                artefact_bucket_name,
                lakehouse_bucket_name,
                sagemaker_role_arn,
                forecast_model_package_group_name,
            )
            destroy_stack_if_state(forecast_sarimax_training_dir)
            sys.exit(0)

        if args.forecast_deepar_training_only:
            context = load_context_outputs(context_dir)
            run(["terraform", f"-chdir={kms_dir}", "init"])
            run(["terraform", f"-chdir={s3_dir}", "init"])
            run(["terraform", f"-chdir={iam_dir}", "init"])
            run(["terraform", f"-chdir={model_registry_dir}", "init"])
            kms_key_arn = get_output(kms_dir, "kms_key_arn")
            artefact_bucket_name = get_output(s3_dir, "artefact_bucket_name")
            lakehouse_bucket_name = get_output(s3_dir, "lakehouse_bucket_name")
            sagemaker_role_arn = get_output(iam_dir, "sagemaker_role_arn")
            forecast_model_package_group_name = get_output(model_registry_dir, "forecast_model_package_group_name")
            write_forecast_deepar_training_tfvars(
                forecast_deepar_training_dir,
                context,
                kms_key_arn,
                artefact_bucket_name,
                lakehouse_bucket_name,
                sagemaker_role_arn,
                forecast_model_package_group_name,
            )
            destroy_stack_if_state(forecast_deepar_training_dir)
            sys.exit(0)

        if args.forecast_tft_training_only:
            context = load_context_outputs(context_dir)
            run(["terraform", f"-chdir={kms_dir}", "init"])
            run(["terraform", f"-chdir={s3_dir}", "init"])
            run(["terraform", f"-chdir={iam_dir}", "init"])
            run(["terraform", f"-chdir={model_registry_dir}", "init"])
            kms_key_arn = get_output(kms_dir, "kms_key_arn")
            artefact_bucket_name = get_output(s3_dir, "artefact_bucket_name")
            lakehouse_bucket_name = get_output(s3_dir, "lakehouse_bucket_name")
            sagemaker_role_arn = get_output(iam_dir, "sagemaker_role_arn")
            forecast_model_package_group_name = get_output(model_registry_dir, "forecast_model_package_group_name")
            write_forecast_tft_training_tfvars(
                forecast_tft_training_dir,
                context,
                kms_key_arn,
                artefact_bucket_name,
                lakehouse_bucket_name,
                sagemaker_role_arn,
                forecast_model_package_group_name,
            )
            destroy_stack_if_state(forecast_tft_training_dir)
            sys.exit(0)

        if args.anomaly_residual_training_only:
            context = load_context_outputs(context_dir)
            run(["terraform", f"-chdir={kms_dir}", "init"])
            run(["terraform", f"-chdir={s3_dir}", "init"])
            run(["terraform", f"-chdir={iam_dir}", "init"])
            run(["terraform", f"-chdir={model_registry_dir}", "init"])
            kms_key_arn = get_output(kms_dir, "kms_key_arn")
            artefact_bucket_name = get_output(s3_dir, "artefact_bucket_name")
            lakehouse_bucket_name = get_output(s3_dir, "lakehouse_bucket_name")
            sagemaker_role_arn = get_output(iam_dir, "sagemaker_role_arn")
            anomaly_model_package_group_name = get_output(model_registry_dir, "anomaly_model_package_group_name")
            write_anomaly_residual_training_tfvars(
                anomaly_residual_training_dir,
                context,
                kms_key_arn,
                artefact_bucket_name,
                lakehouse_bucket_name,
                sagemaker_role_arn,
                anomaly_model_package_group_name,
            )
            destroy_stack_if_state(anomaly_residual_training_dir)
            sys.exit(0)

        if args.anomaly_one_class_svm_training_only:
            context = load_context_outputs(context_dir)
            run(["terraform", f"-chdir={kms_dir}", "init"])
            run(["terraform", f"-chdir={s3_dir}", "init"])
            run(["terraform", f"-chdir={iam_dir}", "init"])
            run(["terraform", f"-chdir={model_registry_dir}", "init"])
            kms_key_arn = get_output(kms_dir, "kms_key_arn")
            artefact_bucket_name = get_output(s3_dir, "artefact_bucket_name")
            lakehouse_bucket_name = get_output(s3_dir, "lakehouse_bucket_name")
            sagemaker_role_arn = get_output(iam_dir, "sagemaker_role_arn")
            anomaly_model_package_group_name = get_output(model_registry_dir, "anomaly_model_package_group_name")
            write_anomaly_one_class_svm_training_tfvars(
                anomaly_one_class_svm_training_dir,
                context,
                kms_key_arn,
                artefact_bucket_name,
                lakehouse_bucket_name,
                sagemaker_role_arn,
                anomaly_model_package_group_name,
            )
            destroy_stack_if_state(anomaly_one_class_svm_training_dir)
            sys.exit(0)

        if args.anomaly_autoencoder_training_only:
            context = load_context_outputs(context_dir)
            run(["terraform", f"-chdir={kms_dir}", "init"])
            run(["terraform", f"-chdir={s3_dir}", "init"])
            run(["terraform", f"-chdir={iam_dir}", "init"])
            run(["terraform", f"-chdir={model_registry_dir}", "init"])
            kms_key_arn = get_output(kms_dir, "kms_key_arn")
            artefact_bucket_name = get_output(s3_dir, "artefact_bucket_name")
            lakehouse_bucket_name = get_output(s3_dir, "lakehouse_bucket_name")
            sagemaker_role_arn = get_output(iam_dir, "sagemaker_role_arn")
            anomaly_model_package_group_name = get_output(model_registry_dir, "anomaly_model_package_group_name")
            write_anomaly_autoencoder_training_tfvars(
                anomaly_autoencoder_training_dir,
                context,
                kms_key_arn,
                artefact_bucket_name,
                lakehouse_bucket_name,
                sagemaker_role_arn,
                anomaly_model_package_group_name,
            )
            destroy_stack_if_state(anomaly_autoencoder_training_dir)
            sys.exit(0)

        if args.forecast_endpoint_only:
            context = load_context_outputs(context_dir)
            run(["terraform", f"-chdir={kms_dir}", "init"])
            run(["terraform", f"-chdir={iam_dir}", "init"])
            run(["terraform", f"-chdir={model_registry_dir}", "init"])
            kms_key_arn = get_output(kms_dir, "kms_key_arn")
            sagemaker_role_arn = get_output(iam_dir, "sagemaker_role_arn")
            forecast_model_package_group_name = get_output(model_registry_dir, "forecast_model_package_group_name")
            write_forecast_endpoint_tfvars(
                forecast_endpoint_dir,
                context,
                kms_key_arn,
                sagemaker_role_arn,
                forecast_model_package_group_name,
            )
            destroy_stack_if_state(forecast_endpoint_dir)
            sys.exit(0)

        if args.anomaly_endpoint_only:
            context = load_context_outputs(context_dir)
            run(["terraform", f"-chdir={kms_dir}", "init"])
            run(["terraform", f"-chdir={iam_dir}", "init"])
            run(["terraform", f"-chdir={model_registry_dir}", "init"])
            kms_key_arn = get_output(kms_dir, "kms_key_arn")
            sagemaker_role_arn = get_output(iam_dir, "sagemaker_role_arn")
            anomaly_model_package_group_name = get_output(model_registry_dir, "anomaly_model_package_group_name")
            write_anomaly_endpoint_tfvars(
                anomaly_endpoint_dir,
                context,
                kms_key_arn,
                sagemaker_role_arn,
                anomaly_model_package_group_name,
            )
            destroy_stack_if_state(anomaly_endpoint_dir)
            sys.exit(0)

        if args.forecast_endpoint_ops_only:
            context = load_context_outputs(context_dir)
            run(["terraform", f"-chdir={forecast_endpoint_dir}", "init"])
            forecast_endpoint_name = get_output(forecast_endpoint_dir, "forecast_endpoint_name")
            forecast_endpoint_variant_name = get_output(forecast_endpoint_dir, "forecast_endpoint_variant_name")
            write_forecast_endpoint_ops_tfvars(
                forecast_endpoint_ops_dir,
                context,
                forecast_endpoint_name,
                forecast_endpoint_variant_name,
            )
            destroy_stack_if_state(forecast_endpoint_ops_dir)
            sys.exit(0)

        if args.model_evaluation_only:
            context = load_context_outputs(context_dir)
            run(["terraform", f"-chdir={kms_dir}", "init"])
            run(["terraform", f"-chdir={s3_dir}", "init"])
            run(["terraform", f"-chdir={model_registry_dir}", "init"])
            kms_key_arn = get_output(kms_dir, "kms_key_arn")
            artefact_bucket_name = get_output(s3_dir, "artefact_bucket_name")
            forecast_model_package_group_name = get_output(model_registry_dir, "forecast_model_package_group_name")
            anomaly_model_package_group_name = get_output(model_registry_dir, "anomaly_model_package_group_name")
            write_model_evaluation_tfvars(
                model_evaluation_dir,
                context,
                kms_key_arn,
                artefact_bucket_name,
                forecast_model_package_group_name,
                anomaly_model_package_group_name,
            )
            destroy_stack_if_state(model_evaluation_dir)
            sys.exit(0)

        if args.anomaly_endpoint_ops_only:
            context = load_context_outputs(context_dir)
            run(["terraform", f"-chdir={anomaly_endpoint_dir}", "init"])
            anomaly_endpoint_name = get_output(anomaly_endpoint_dir, "anomaly_endpoint_name")
            anomaly_endpoint_variant_name = get_output(anomaly_endpoint_dir, "anomaly_endpoint_variant_name")
            write_anomaly_endpoint_ops_tfvars(
                anomaly_endpoint_ops_dir,
                context,
                anomaly_endpoint_name,
                anomaly_endpoint_variant_name,
            )
            destroy_stack_if_state(anomaly_endpoint_ops_dir)
            sys.exit(0)

        context = None
        if tf_state_exists(context_dir):
            context = load_context_outputs(context_dir)

        if context and tf_state_exists(kms_dir):
            write_kms_tfvars(kms_dir, context)

        if context and tf_state_exists(kms_dir) and tf_state_exists(s3_dir):
            run(["terraform", f"-chdir={kms_dir}", "init"])
            kms_key_arn = get_output(kms_dir, "kms_key_arn")
            write_s3_tfvars(s3_dir, context, kms_key_arn)

        if context and tf_state_exists(kms_dir) and tf_state_exists(s3_dir) and tf_state_exists(iam_dir):
            run(["terraform", f"-chdir={kms_dir}", "init"])
            run(["terraform", f"-chdir={s3_dir}", "init"])
            kms_key_arn = get_output(kms_dir, "kms_key_arn")
            lakehouse_bucket_arn = get_output(s3_dir, "lakehouse_bucket_arn")
            artefact_bucket_arn = get_output(s3_dir, "artefact_bucket_arn")
            monitoring_bucket_arn = get_output(s3_dir, "monitoring_bucket_arn")
            write_iam_tfvars(
                iam_dir,
                context,
                kms_key_arn,
                lakehouse_bucket_arn,
                artefact_bucket_arn,
                monitoring_bucket_arn,
            )

        if context and tf_state_exists(kms_dir) and tf_state_exists(s3_dir) and tf_state_exists(iam_dir) and tf_state_exists(lambda_dir):
            run(["terraform", f"-chdir={kms_dir}", "init"])
            run(["terraform", f"-chdir={s3_dir}", "init"])
            run(["terraform", f"-chdir={iam_dir}", "init"])
            kms_key_arn = get_output(kms_dir, "kms_key_arn")
            lambda_role_arn = get_output(iam_dir, "lambda_role_arn")
            lakehouse_bucket_name = get_output(s3_dir, "lakehouse_bucket_name")
            write_lambda_tfvars(
                lambda_dir,
                context,
                kms_key_arn,
                lambda_role_arn,
                lakehouse_bucket_name,
            )

        if context and tf_state_exists(lambda_dir) and tf_state_exists(scheduler_dir):
            run(["terraform", f"-chdir={lambda_dir}", "init"])
            lambda_function_name = get_output(lambda_dir, "lambda_function_name")
            lambda_function_arn = get_output(lambda_dir, "lambda_function_arn")
            write_scheduler_tfvars(
                scheduler_dir,
                context,
                lambda_function_name,
                lambda_function_arn,
            )

        if context and tf_state_exists(s3_dir) and tf_state_exists(glue_catalog_dir):
            run(["terraform", f"-chdir={s3_dir}", "init"])
            lakehouse_bucket_name = get_output(s3_dir, "lakehouse_bucket_name")
            write_glue_catalog_tfvars(
                glue_catalog_dir,
                context,
                lakehouse_bucket_name,
            )

        if (
            context
            and tf_state_exists(kms_dir)
            and tf_state_exists(s3_dir)
            and tf_state_exists(iam_dir)
            and tf_state_exists(glue_catalog_dir)
            and tf_state_exists(glue_bronze_silver_dir)
        ):
            run(["terraform", f"-chdir={kms_dir}", "init"])
            run(["terraform", f"-chdir={s3_dir}", "init"])
            run(["terraform", f"-chdir={iam_dir}", "init"])
            run(["terraform", f"-chdir={glue_catalog_dir}", "init"])
            kms_key_arn = get_output(kms_dir, "kms_key_arn")
            glue_role_arn = get_output(iam_dir, "glue_role_arn")
            lakehouse_bucket_name = get_output(s3_dir, "lakehouse_bucket_name")
            artefact_bucket_name = get_output(s3_dir, "artefact_bucket_name")
            glue_database_name = get_output(glue_catalog_dir, "glue_database_name")
            energy_table_name = get_output(glue_catalog_dir, "energy_table_name")
            weather_table_name = get_output(glue_catalog_dir, "weather_table_name")
            write_glue_bronze_silver_tfvars(
                glue_bronze_silver_dir,
                context,
                kms_key_arn,
                glue_role_arn,
                lakehouse_bucket_name,
                artefact_bucket_name,
                glue_database_name,
                energy_table_name,
                weather_table_name,
            )

        if context and tf_state_exists(glue_bronze_silver_dir) and tf_state_exists(glue_bronze_silver_scheduler_dir):
            run(["terraform", f"-chdir={glue_bronze_silver_dir}", "init"])
            glue_job_name = get_output(glue_bronze_silver_dir, "glue_job_name")
            glue_job_arn = get_output(glue_bronze_silver_dir, "glue_job_arn")
            write_glue_bronze_silver_scheduler_tfvars(
                glue_bronze_silver_scheduler_dir,
                context,
                glue_job_name,
                glue_job_arn,
            )

        if context and tf_state_exists(kms_dir) and tf_state_exists(s3_dir) and tf_state_exists(iam_dir) and tf_state_exists(glue_silver_gold_dir):
            run(["terraform", f"-chdir={kms_dir}", "init"])
            run(["terraform", f"-chdir={s3_dir}", "init"])
            run(["terraform", f"-chdir={iam_dir}", "init"])
            kms_key_arn = get_output(kms_dir, "kms_key_arn")
            glue_role_arn = get_output(iam_dir, "glue_role_arn")
            lakehouse_bucket_name = get_output(s3_dir, "lakehouse_bucket_name")
            artefact_bucket_name = get_output(s3_dir, "artefact_bucket_name")
            write_glue_silver_gold_tfvars(
                glue_silver_gold_dir,
                context,
                kms_key_arn,
                glue_role_arn,
                lakehouse_bucket_name,
                artefact_bucket_name,
            )

        if context and tf_state_exists(glue_silver_gold_dir) and tf_state_exists(glue_silver_gold_scheduler_dir):
            run(["terraform", f"-chdir={glue_silver_gold_dir}", "init"])
            glue_job_name = get_output(glue_silver_gold_dir, "glue_job_name")
            glue_job_arn = get_output(glue_silver_gold_dir, "glue_job_arn")
            write_glue_silver_gold_scheduler_tfvars(
                glue_silver_gold_scheduler_dir,
                context,
                glue_job_name,
                glue_job_arn,
            )

        if context and tf_state_exists(model_registry_dir):
            write_model_registry_tfvars(model_registry_dir, context)

        if context and tf_state_exists(kms_dir) and tf_state_exists(iam_dir) and tf_state_exists(studio_domain_dir):
            run(["terraform", f"-chdir={kms_dir}", "init"])
            run(["terraform", f"-chdir={iam_dir}", "init"])
            kms_key_arn = get_output(kms_dir, "kms_key_arn")
            sagemaker_role_arn = get_output(iam_dir, "sagemaker_role_arn")
            write_studio_domain_tfvars(
                studio_domain_dir,
                context,
                kms_key_arn,
                sagemaker_role_arn,
            )

        if (
            context
            and tf_state_exists(kms_dir)
            and tf_state_exists(s3_dir)
            and tf_state_exists(iam_dir)
            and tf_state_exists(model_registry_dir)
            and tf_state_exists(forecast_training_dir)
        ):
            run(["terraform", f"-chdir={kms_dir}", "init"])
            run(["terraform", f"-chdir={s3_dir}", "init"])
            run(["terraform", f"-chdir={iam_dir}", "init"])
            run(["terraform", f"-chdir={model_registry_dir}", "init"])
            kms_key_arn = get_output(kms_dir, "kms_key_arn")
            artefact_bucket_name = get_output(s3_dir, "artefact_bucket_name")
            lakehouse_bucket_name = get_output(s3_dir, "lakehouse_bucket_name")
            sagemaker_role_arn = get_output(iam_dir, "sagemaker_role_arn")
            forecast_model_package_group_name = get_output(model_registry_dir, "forecast_model_package_group_name")
            write_forecast_training_tfvars(
                forecast_training_dir,
                context,
                kms_key_arn,
                artefact_bucket_name,
                lakehouse_bucket_name,
                sagemaker_role_arn,
                forecast_model_package_group_name,
            )

        if (
            context
            and tf_state_exists(kms_dir)
            and tf_state_exists(s3_dir)
            and tf_state_exists(iam_dir)
            and tf_state_exists(model_registry_dir)
            and tf_state_exists(forecast_sarimax_training_dir)
        ):
            run(["terraform", f"-chdir={kms_dir}", "init"])
            run(["terraform", f"-chdir={s3_dir}", "init"])
            run(["terraform", f"-chdir={iam_dir}", "init"])
            run(["terraform", f"-chdir={model_registry_dir}", "init"])
            kms_key_arn = get_output(kms_dir, "kms_key_arn")
            artefact_bucket_name = get_output(s3_dir, "artefact_bucket_name")
            lakehouse_bucket_name = get_output(s3_dir, "lakehouse_bucket_name")
            sagemaker_role_arn = get_output(iam_dir, "sagemaker_role_arn")
            forecast_model_package_group_name = get_output(model_registry_dir, "forecast_model_package_group_name")
            write_forecast_sarimax_training_tfvars(
                forecast_sarimax_training_dir,
                context,
                kms_key_arn,
                artefact_bucket_name,
                lakehouse_bucket_name,
                sagemaker_role_arn,
                forecast_model_package_group_name,
            )

        if (
            context
            and tf_state_exists(kms_dir)
            and tf_state_exists(s3_dir)
            and tf_state_exists(iam_dir)
            and tf_state_exists(model_registry_dir)
            and tf_state_exists(forecast_deepar_training_dir)
        ):
            run(["terraform", f"-chdir={kms_dir}", "init"])
            run(["terraform", f"-chdir={s3_dir}", "init"])
            run(["terraform", f"-chdir={iam_dir}", "init"])
            run(["terraform", f"-chdir={model_registry_dir}", "init"])
            kms_key_arn = get_output(kms_dir, "kms_key_arn")
            artefact_bucket_name = get_output(s3_dir, "artefact_bucket_name")
            lakehouse_bucket_name = get_output(s3_dir, "lakehouse_bucket_name")
            sagemaker_role_arn = get_output(iam_dir, "sagemaker_role_arn")
            forecast_model_package_group_name = get_output(model_registry_dir, "forecast_model_package_group_name")
            write_forecast_deepar_training_tfvars(
                forecast_deepar_training_dir,
                context,
                kms_key_arn,
                artefact_bucket_name,
                lakehouse_bucket_name,
                sagemaker_role_arn,
                forecast_model_package_group_name,
            )

        if (
            context
            and tf_state_exists(kms_dir)
            and tf_state_exists(s3_dir)
            and tf_state_exists(iam_dir)
            and tf_state_exists(model_registry_dir)
            and tf_state_exists(forecast_tft_training_dir)
        ):
            run(["terraform", f"-chdir={kms_dir}", "init"])
            run(["terraform", f"-chdir={s3_dir}", "init"])
            run(["terraform", f"-chdir={iam_dir}", "init"])
            run(["terraform", f"-chdir={model_registry_dir}", "init"])
            kms_key_arn = get_output(kms_dir, "kms_key_arn")
            artefact_bucket_name = get_output(s3_dir, "artefact_bucket_name")
            lakehouse_bucket_name = get_output(s3_dir, "lakehouse_bucket_name")
            sagemaker_role_arn = get_output(iam_dir, "sagemaker_role_arn")
            forecast_model_package_group_name = get_output(model_registry_dir, "forecast_model_package_group_name")
            write_forecast_tft_training_tfvars(
                forecast_tft_training_dir,
                context,
                kms_key_arn,
                artefact_bucket_name,
                lakehouse_bucket_name,
                sagemaker_role_arn,
                forecast_model_package_group_name,
            )

        if (
            context
            and tf_state_exists(kms_dir)
            and tf_state_exists(s3_dir)
            and tf_state_exists(iam_dir)
            and tf_state_exists(model_registry_dir)
            and tf_state_exists(anomaly_residual_training_dir)
        ):
            run(["terraform", f"-chdir={kms_dir}", "init"])
            run(["terraform", f"-chdir={s3_dir}", "init"])
            run(["terraform", f"-chdir={iam_dir}", "init"])
            run(["terraform", f"-chdir={model_registry_dir}", "init"])
            kms_key_arn = get_output(kms_dir, "kms_key_arn")
            artefact_bucket_name = get_output(s3_dir, "artefact_bucket_name")
            lakehouse_bucket_name = get_output(s3_dir, "lakehouse_bucket_name")
            sagemaker_role_arn = get_output(iam_dir, "sagemaker_role_arn")
            anomaly_model_package_group_name = get_output(model_registry_dir, "anomaly_model_package_group_name")
            write_anomaly_residual_training_tfvars(
                anomaly_residual_training_dir,
                context,
                kms_key_arn,
                artefact_bucket_name,
                lakehouse_bucket_name,
                sagemaker_role_arn,
                anomaly_model_package_group_name,
            )

        if (
            context
            and tf_state_exists(kms_dir)
            and tf_state_exists(s3_dir)
            and tf_state_exists(iam_dir)
            and tf_state_exists(model_registry_dir)
            and tf_state_exists(anomaly_one_class_svm_training_dir)
        ):
            run(["terraform", f"-chdir={kms_dir}", "init"])
            run(["terraform", f"-chdir={s3_dir}", "init"])
            run(["terraform", f"-chdir={iam_dir}", "init"])
            run(["terraform", f"-chdir={model_registry_dir}", "init"])
            kms_key_arn = get_output(kms_dir, "kms_key_arn")
            artefact_bucket_name = get_output(s3_dir, "artefact_bucket_name")
            lakehouse_bucket_name = get_output(s3_dir, "lakehouse_bucket_name")
            sagemaker_role_arn = get_output(iam_dir, "sagemaker_role_arn")
            anomaly_model_package_group_name = get_output(model_registry_dir, "anomaly_model_package_group_name")
            write_anomaly_one_class_svm_training_tfvars(
                anomaly_one_class_svm_training_dir,
                context,
                kms_key_arn,
                artefact_bucket_name,
                lakehouse_bucket_name,
                sagemaker_role_arn,
                anomaly_model_package_group_name,
            )

        if (
            context
            and tf_state_exists(kms_dir)
            and tf_state_exists(s3_dir)
            and tf_state_exists(iam_dir)
            and tf_state_exists(model_registry_dir)
            and tf_state_exists(anomaly_autoencoder_training_dir)
        ):
            run(["terraform", f"-chdir={kms_dir}", "init"])
            run(["terraform", f"-chdir={s3_dir}", "init"])
            run(["terraform", f"-chdir={iam_dir}", "init"])
            run(["terraform", f"-chdir={model_registry_dir}", "init"])
            kms_key_arn = get_output(kms_dir, "kms_key_arn")
            artefact_bucket_name = get_output(s3_dir, "artefact_bucket_name")
            lakehouse_bucket_name = get_output(s3_dir, "lakehouse_bucket_name")
            sagemaker_role_arn = get_output(iam_dir, "sagemaker_role_arn")
            anomaly_model_package_group_name = get_output(model_registry_dir, "anomaly_model_package_group_name")
            write_anomaly_autoencoder_training_tfvars(
                anomaly_autoencoder_training_dir,
                context,
                kms_key_arn,
                artefact_bucket_name,
                lakehouse_bucket_name,
                sagemaker_role_arn,
                anomaly_model_package_group_name,
            )

        if (
            context
            and tf_state_exists(kms_dir)
            and tf_state_exists(s3_dir)
            and tf_state_exists(iam_dir)
            and tf_state_exists(model_registry_dir)
            and tf_state_exists(anomaly_training_dir)
        ):
            run(["terraform", f"-chdir={kms_dir}", "init"])
            run(["terraform", f"-chdir={s3_dir}", "init"])
            run(["terraform", f"-chdir={iam_dir}", "init"])
            run(["terraform", f"-chdir={model_registry_dir}", "init"])
            kms_key_arn = get_output(kms_dir, "kms_key_arn")
            artefact_bucket_name = get_output(s3_dir, "artefact_bucket_name")
            lakehouse_bucket_name = get_output(s3_dir, "lakehouse_bucket_name")
            sagemaker_role_arn = get_output(iam_dir, "sagemaker_role_arn")
            anomaly_model_package_group_name = get_output(model_registry_dir, "anomaly_model_package_group_name")
            write_anomaly_training_tfvars(
                anomaly_training_dir,
                context,
                kms_key_arn,
                artefact_bucket_name,
                lakehouse_bucket_name,
                sagemaker_role_arn,
                anomaly_model_package_group_name,
            )

        if (
            context
            and tf_state_exists(forecast_endpoint_dir)
            and tf_state_exists(forecast_endpoint_ops_dir)
        ):
            run(["terraform", f"-chdir={forecast_endpoint_dir}", "init"])
            forecast_endpoint_name = get_output(forecast_endpoint_dir, "forecast_endpoint_name")
            forecast_endpoint_variant_name = get_output(forecast_endpoint_dir, "forecast_endpoint_variant_name")
            write_forecast_endpoint_ops_tfvars(
                forecast_endpoint_ops_dir,
                context,
                forecast_endpoint_name,
                forecast_endpoint_variant_name,
            )

        if (
            context
            and tf_state_exists(kms_dir)
            and tf_state_exists(s3_dir)
            and tf_state_exists(model_registry_dir)
            and tf_state_exists(model_evaluation_dir)
        ):
            run(["terraform", f"-chdir={kms_dir}", "init"])
            run(["terraform", f"-chdir={s3_dir}", "init"])
            run(["terraform", f"-chdir={model_registry_dir}", "init"])
            kms_key_arn = get_output(kms_dir, "kms_key_arn")
            artefact_bucket_name = get_output(s3_dir, "artefact_bucket_name")
            forecast_model_package_group_name = get_output(model_registry_dir, "forecast_model_package_group_name")
            anomaly_model_package_group_name = get_output(model_registry_dir, "anomaly_model_package_group_name")
            write_model_evaluation_tfvars(
                model_evaluation_dir,
                context,
                kms_key_arn,
                artefact_bucket_name,
                forecast_model_package_group_name,
                anomaly_model_package_group_name,
            )

        if (
            context
            and tf_state_exists(kms_dir)
            and tf_state_exists(iam_dir)
            and tf_state_exists(model_registry_dir)
            and tf_state_exists(forecast_endpoint_dir)
        ):
            run(["terraform", f"-chdir={kms_dir}", "init"])
            run(["terraform", f"-chdir={iam_dir}", "init"])
            run(["terraform", f"-chdir={model_registry_dir}", "init"])
            kms_key_arn = get_output(kms_dir, "kms_key_arn")
            sagemaker_role_arn = get_output(iam_dir, "sagemaker_role_arn")
            forecast_model_package_group_name = get_output(model_registry_dir, "forecast_model_package_group_name")
            write_forecast_endpoint_tfvars(
                forecast_endpoint_dir,
                context,
                kms_key_arn,
                sagemaker_role_arn,
                forecast_model_package_group_name,
            )

        if (
            context
            and tf_state_exists(kms_dir)
            and tf_state_exists(iam_dir)
            and tf_state_exists(model_registry_dir)
            and tf_state_exists(anomaly_endpoint_dir)
        ):
            run(["terraform", f"-chdir={kms_dir}", "init"])
            run(["terraform", f"-chdir={iam_dir}", "init"])
            run(["terraform", f"-chdir={model_registry_dir}", "init"])
            kms_key_arn = get_output(kms_dir, "kms_key_arn")
            sagemaker_role_arn = get_output(iam_dir, "sagemaker_role_arn")
            anomaly_model_package_group_name = get_output(model_registry_dir, "anomaly_model_package_group_name")
            write_anomaly_endpoint_tfvars(
                anomaly_endpoint_dir,
                context,
                kms_key_arn,
                sagemaker_role_arn,
                anomaly_model_package_group_name,
            )

        if (
            context
            and tf_state_exists(anomaly_endpoint_dir)
            and tf_state_exists(anomaly_endpoint_ops_dir)
        ):
            run(["terraform", f"-chdir={anomaly_endpoint_dir}", "init"])
            anomaly_endpoint_name = get_output(anomaly_endpoint_dir, "anomaly_endpoint_name")
            anomaly_endpoint_variant_name = get_output(anomaly_endpoint_dir, "anomaly_endpoint_variant_name")
            write_anomaly_endpoint_ops_tfvars(
                anomaly_endpoint_ops_dir,
                context,
                anomaly_endpoint_name,
                anomaly_endpoint_variant_name,
            )

        destroy_stack_if_state(anomaly_endpoint_ops_dir)
        destroy_stack_if_state(model_evaluation_dir)
        destroy_stack_if_state(forecast_endpoint_ops_dir)
        destroy_stack_if_state(anomaly_endpoint_dir)
        destroy_stack_if_state(forecast_endpoint_dir)
        destroy_stack_if_state(anomaly_autoencoder_training_dir)
        destroy_stack_if_state(anomaly_one_class_svm_training_dir)
        destroy_stack_if_state(anomaly_residual_training_dir)
        destroy_stack_if_state(forecast_tft_training_dir)
        destroy_stack_if_state(forecast_deepar_training_dir)
        destroy_stack_if_state(forecast_sarimax_training_dir)
        destroy_stack_if_state(anomaly_training_dir)
        destroy_stack_if_state(forecast_training_dir)
        destroy_stack_if_state(studio_domain_dir)
        destroy_stack_if_state(model_registry_dir)
        destroy_stack_if_state(glue_silver_gold_scheduler_dir)
        destroy_stack_if_state(glue_silver_gold_dir)
        destroy_stack_if_state(glue_bronze_silver_scheduler_dir)
        destroy_stack_if_state(glue_bronze_silver_dir)
        destroy_stack_if_state(glue_catalog_dir)
        destroy_stack_if_state(scheduler_dir)
        destroy_stack_if_state(lambda_dir)
        destroy_stack_if_state(iam_dir)
        destroy_stack_if_state(s3_dir)
        destroy_stack_if_state(kms_dir)
        destroy_stack_if_state(context_dir)

    except subprocess.CalledProcessError as exc:
        print(f"Command failed: {exc}")
        sys.exit(exc.returncode)
