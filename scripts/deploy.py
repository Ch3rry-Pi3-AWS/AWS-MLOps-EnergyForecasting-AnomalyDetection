"""Deployment helper for the AWS energy forecasting project.

This script orchestrates the Terraform modules in the intended dependency
order so that later modules can automatically consume outputs from earlier
ones. The main goal is to minimise manual editing of `terraform.tfvars`
files while preserving the per-resource Terraform layout used across the
repository.

Notes
-----
- The script loads a local `.env` file if one exists.
- Each module receives a generated `terraform.tfvars` file immediately
  before deployment.
- The script deliberately deploys modules in dependency order:

    1. Project context
    2. KMS
    3. S3 lakehouse
    4. IAM foundation
    5. Lambda ingestion
    6. EventBridge Scheduler
    7. Glue catalogue
    8. Glue Bronze-to-Silver job
    9. Glue Bronze-to-Silver scheduler
    10. Glue Silver-to-Gold job
    11. Glue Silver-to-Gold scheduler
    12. SageMaker model registry
    13. SageMaker Studio domain
    14. SageMaker forecast training assets
    15. SageMaker anomaly training assets
    16. SageMaker forecast endpoint configuration
    17. SageMaker anomaly endpoint configuration
    18. SageMaker forecast endpoint operations
    19. SageMaker model evaluation
    20. SageMaker anomaly endpoint operations
    21. SageMaker forecast SARIMAX training assets
    22. SageMaker forecast DeepAR training assets
    23. SageMaker forecast TFT training assets
    24. SageMaker anomaly residual-scoring training assets
    25. SageMaker anomaly One-Class SVM training assets
    26. SageMaker anomaly autoencoder training assets

- Full deployment applies every module in sequence.
- Targeted deployment flags only apply the named module, assuming its
  upstream dependencies have already been deployed.

Examples
--------
Deploy the full stack built so far:

>>> # python scripts/deploy.py

Deploy only the Bronze-to-Silver Glue job after its dependencies exist:

>>> # python scripts/deploy.py --bronze-silver-only

Deploy only the Bronze-to-Silver scheduler after the Glue job exists:

>>> # python scripts/deploy.py --bronze-silver-scheduler-only

Deploy only the Silver-to-Gold Glue job after the Silver layer exists:

>>> # python scripts/deploy.py --silver-gold-only

Deploy only the Silver-to-Gold scheduler after the Gold job exists:

>>> # python scripts/deploy.py --silver-gold-scheduler-only

Deploy only the SageMaker model registry after the shared context exists:

>>> # python scripts/deploy.py --model-registry-only

Deploy only the SageMaker Studio domain after KMS and IAM exist:

>>> # python scripts/deploy.py --studio-domain-only

Deploy only the forecast-training asset stage after model registry exists:

>>> # python scripts/deploy.py --forecast-training-only

Deploy only the anomaly-training asset stage after model registry exists:

>>> # python scripts/deploy.py --anomaly-training-only

Deploy only the SARIMAX forecast-training asset stage after model registry exists:

>>> # python scripts/deploy.py --forecast-sarimax-training-only

Deploy only the DeepAR forecast-training asset stage after model registry exists:

>>> # python scripts/deploy.py --forecast-deepar-training-only

Deploy only the TFT forecast-training asset stage after model registry exists:

>>> # python scripts/deploy.py --forecast-tft-training-only

Deploy only the anomaly residual-scoring training asset stage after model registry exists:

>>> # python scripts/deploy.py --anomaly-residual-training-only

Deploy only the anomaly One-Class SVM training asset stage after model registry exists:

>>> # python scripts/deploy.py --anomaly-one-class-svm-training-only

Deploy only the anomaly autoencoder training asset stage after model registry exists:

>>> # python scripts/deploy.py --anomaly-autoencoder-training-only

Deploy only the forecast-endpoint configuration after model registry exists:

>>> # python scripts/deploy.py --forecast-endpoint-only

Deploy only the anomaly-endpoint configuration after model registry exists:

>>> # python scripts/deploy.py --anomaly-endpoint-only

Deploy only the forecast-endpoint operations stage after the endpoint exists:

>>> # python scripts/deploy.py --forecast-endpoint-ops-only

Deploy only the model-evaluation configuration stage after model registry and
artefact storage exist:

>>> # python scripts/deploy.py --model-evaluation-only

Deploy only the anomaly-endpoint operations stage after the endpoint exists:

>>> # python scripts/deploy.py --anomaly-endpoint-ops-only
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

DEFAULTS = {
    "aws_region": "eu-west-2",
    "environment": "dev",
    "project_name": "Real-Time Energy Forecasting and Anomaly Detection",
    "project_slug": "energy-forecast",
    "resource_prefix": "energyops",
    "owner": "portfolio",
    "cost_centre": "mlops-lab",
}


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
    - Existing environment variables are not overwritten.
    - Blank lines and comments are ignored.
    - The parser is intentionally simple because the project only needs
      straightforward `KEY=value` pairs.

    Examples
    --------
    >>> from pathlib import Path
    >>> load_env_file(Path(".env"))  # doctest: +SKIP
    """

    if not path.exists():
        return

    # Read the file line by line so that comments and empty rows can be
    # skipped without needing a separate dependency such as python-dotenv.
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

    Notes
    -----
    This helper only supports the value shapes used by this repository:
    scalars, dictionaries, and simple lists or tuples.

    Examples
    --------
    >>> hcl_value(True)
    'true'
    >>> hcl_value({"Environment": "dev"})
    '{ Environment = "dev" }'
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

    Raises
    ------
    RuntimeError
        If the output cannot be found.
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

    Notes
    -----
    The CLI path is tried first because it reflects Terraform's official
    output handling. Local state parsing is used as a fallback when the
    module has already been applied but direct CLI output is unavailable.
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


def env_or_default(env_name: str, default_value: str) -> str:
    """
    Read an environment variable with a fallback default.

    Parameters
    ----------
    env_name : str
        Environment variable name.
    default_value : str
        Value used when the environment variable is missing.

    Returns
    -------
    str
        Environment value or the supplied default.
    """

    return os.environ.get(env_name, default_value)


def build_context_defaults() -> dict[str, str]:
    """
    Build the shared deployment context from environment variables.

    Returns
    -------
    dict[str, str]
        Context values consumed by the project context module.

    Examples
    --------
    >>> "aws_region" in build_context_defaults()
    True
    """

    return {
        "aws_region": env_or_default("AWS_REGION", DEFAULTS["aws_region"]),
        "environment": env_or_default("PROJECT_ENV", DEFAULTS["environment"]),
        "project_name": env_or_default("PROJECT_NAME", DEFAULTS["project_name"]),
        "project_slug": env_or_default("PROJECT_SLUG", DEFAULTS["project_slug"]),
        "resource_prefix": env_or_default("RESOURCE_PREFIX", DEFAULTS["resource_prefix"]),
        "owner": env_or_default("OWNER", DEFAULTS["owner"]),
        "cost_centre": env_or_default("COST_CENTRE", DEFAULTS["cost_centre"]),
    }


def write_context_tfvars(context_dir: Path) -> None:
    """
    Write the live variables file for the project context module.

    Parameters
    ----------
    context_dir : Path
        Terraform directory for `01_project_context`.
    """

    context = build_context_defaults()
    items = [
        ("aws_region", context["aws_region"]),
        ("environment", context["environment"]),
        ("project_name", context["project_name"]),
        ("project_slug", context["project_slug"]),
        ("resource_prefix", context["resource_prefix"]),
        ("owner", context["owner"]),
        ("cost_centre", context["cost_centre"]),
        ("extra_tags", {}),
    ]
    write_tfvars(context_dir / "terraform.tfvars", items)


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

    # Initialise first so Terraform knows about the required providers
    # and can read the output values consistently.
    run(["terraform", f"-chdir={context_dir}", "init"])
    return {
        "aws_region": get_output(context_dir, "aws_region"),
        "environment": get_output(context_dir, "environment"),
        "project_name": get_output(context_dir, "project_name"),
        "project_slug": get_output(context_dir, "project_slug"),
        "resource_prefix": get_output(context_dir, "resource_prefix"),
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


def deploy_stack(tf_dir: Path) -> None:
    """
    Initialise and apply a Terraform module.

    Parameters
    ----------
    tf_dir : Path
        Terraform module directory.

    Raises
    ------
    FileNotFoundError
        If the module directory does not exist.
    """

    if not tf_dir.exists():
        raise FileNotFoundError(f"Missing Terraform dir: {tf_dir}")

    # Each module is initialised immediately before apply so the script can
    # be run incrementally without assuming prior manual Terraform commands.
    run(["terraform", f"-chdir={tf_dir}", "init"])
    run(["terraform", f"-chdir={tf_dir}", "apply", "-auto-approve"])


if __name__ == "__main__":
    try:
        parser = argparse.ArgumentParser(
            description="Deploy Terraform stacks for the AWS energy forecasting foundation layer."
        )
        group = parser.add_mutually_exclusive_group()
        group.add_argument("--context-only", action="store_true", help="Deploy only the project context")
        group.add_argument("--kms-only", action="store_true", help="Deploy only the KMS stack")
        group.add_argument("--s3-only", action="store_true", help="Deploy only the S3 lakehouse stack")
        group.add_argument("--iam-only", action="store_true", help="Deploy only the IAM foundation stack")
        group.add_argument("--lambda-only", action="store_true", help="Deploy only the ingestion Lambda stack")
        group.add_argument("--scheduler-only", action="store_true", help="Deploy only the EventBridge Scheduler stack")
        group.add_argument("--glue-catalog-only", action="store_true", help="Deploy only the Glue catalogue stack")
        group.add_argument("--bronze-silver-only", action="store_true", help="Deploy only the Glue Bronze-to-Silver job")
        group.add_argument(
            "--bronze-silver-scheduler-only",
            action="store_true",
            help="Deploy only the Bronze-to-Silver scheduler stack",
        )
        group.add_argument("--silver-gold-only", action="store_true", help="Deploy only the Glue Silver-to-Gold job")
        group.add_argument(
            "--silver-gold-scheduler-only",
            action="store_true",
            help="Deploy only the Silver-to-Gold scheduler stack",
        )
        group.add_argument("--model-registry-only", action="store_true", help="Deploy only the SageMaker model registry stack")
        group.add_argument("--studio-domain-only", action="store_true", help="Deploy only the SageMaker Studio domain stack")
        group.add_argument("--forecast-training-only", action="store_true", help="Deploy only the SageMaker forecast training asset stack")
        group.add_argument("--anomaly-training-only", action="store_true", help="Deploy only the SageMaker anomaly training asset stack")
        group.add_argument("--forecast-sarimax-training-only", action="store_true", help="Deploy only the SageMaker forecast SARIMAX training asset stack")
        group.add_argument("--forecast-deepar-training-only", action="store_true", help="Deploy only the SageMaker forecast DeepAR training asset stack")
        group.add_argument("--forecast-tft-training-only", action="store_true", help="Deploy only the SageMaker forecast TFT training asset stack")
        group.add_argument("--anomaly-residual-training-only", action="store_true", help="Deploy only the SageMaker anomaly residual-scoring training asset stack")
        group.add_argument("--anomaly-one-class-svm-training-only", action="store_true", help="Deploy only the SageMaker anomaly One-Class SVM training asset stack")
        group.add_argument("--anomaly-autoencoder-training-only", action="store_true", help="Deploy only the SageMaker anomaly autoencoder training asset stack")
        group.add_argument("--forecast-endpoint-only", action="store_true", help="Deploy only the SageMaker forecast endpoint configuration stack")
        group.add_argument("--anomaly-endpoint-only", action="store_true", help="Deploy only the SageMaker anomaly endpoint configuration stack")
        group.add_argument("--forecast-endpoint-ops-only", action="store_true", help="Deploy only the SageMaker forecast endpoint monitoring and autoscaling stack")
        group.add_argument("--model-evaluation-only", action="store_true", help="Deploy only the SageMaker model-evaluation configuration stack")
        group.add_argument("--anomaly-endpoint-ops-only", action="store_true", help="Deploy only the SageMaker anomaly endpoint monitoring and autoscaling stack")
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
            write_context_tfvars(context_dir)
            deploy_stack(context_dir)
            sys.exit(0)

        if args.kms_only:
            context = load_context_outputs(context_dir)
            write_kms_tfvars(kms_dir, context)
            deploy_stack(kms_dir)
            sys.exit(0)

        if args.s3_only:
            context = load_context_outputs(context_dir)
            run(["terraform", f"-chdir={kms_dir}", "init"])
            kms_key_arn = get_output(kms_dir, "kms_key_arn")
            write_s3_tfvars(s3_dir, context, kms_key_arn)
            deploy_stack(s3_dir)
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
            deploy_stack(iam_dir)
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
            deploy_stack(lambda_dir)
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
            deploy_stack(scheduler_dir)
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
            deploy_stack(glue_catalog_dir)
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
            deploy_stack(glue_bronze_silver_dir)
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
            deploy_stack(glue_bronze_silver_scheduler_dir)
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
            deploy_stack(glue_silver_gold_dir)
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
            deploy_stack(glue_silver_gold_scheduler_dir)
            sys.exit(0)

        if args.model_registry_only:
            context = load_context_outputs(context_dir)
            write_model_registry_tfvars(model_registry_dir, context)
            deploy_stack(model_registry_dir)
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
            deploy_stack(studio_domain_dir)
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
            deploy_stack(forecast_training_dir)
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
            deploy_stack(anomaly_training_dir)
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
            deploy_stack(forecast_sarimax_training_dir)
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
            deploy_stack(forecast_deepar_training_dir)
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
            deploy_stack(forecast_tft_training_dir)
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
            deploy_stack(anomaly_residual_training_dir)
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
            deploy_stack(anomaly_one_class_svm_training_dir)
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
            deploy_stack(anomaly_autoencoder_training_dir)
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
            deploy_stack(forecast_endpoint_dir)
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
            deploy_stack(anomaly_endpoint_dir)
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
            deploy_stack(forecast_endpoint_ops_dir)
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
            deploy_stack(model_evaluation_dir)
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
            deploy_stack(anomaly_endpoint_ops_dir)
            sys.exit(0)

        write_context_tfvars(context_dir)
        deploy_stack(context_dir)
        context = load_context_outputs(context_dir)

        write_kms_tfvars(kms_dir, context)
        deploy_stack(kms_dir)
        kms_key_arn = get_output(kms_dir, "kms_key_arn")

        write_s3_tfvars(s3_dir, context, kms_key_arn)
        deploy_stack(s3_dir)
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
        deploy_stack(iam_dir)
        lambda_role_arn = get_output(iam_dir, "lambda_role_arn")
        sagemaker_role_arn = get_output(iam_dir, "sagemaker_role_arn")
        lakehouse_bucket_name = get_output(s3_dir, "lakehouse_bucket_name")
        write_lambda_tfvars(
            lambda_dir,
            context,
            kms_key_arn,
            lambda_role_arn,
            lakehouse_bucket_name,
        )
        deploy_stack(lambda_dir)
        lambda_function_name = get_output(lambda_dir, "lambda_function_name")
        lambda_function_arn = get_output(lambda_dir, "lambda_function_arn")
        write_scheduler_tfvars(
            scheduler_dir,
            context,
            lambda_function_name,
            lambda_function_arn,
        )
        deploy_stack(scheduler_dir)

        write_glue_catalog_tfvars(
            glue_catalog_dir,
            context,
            lakehouse_bucket_name,
        )
        deploy_stack(glue_catalog_dir)
        glue_database_name = get_output(glue_catalog_dir, "glue_database_name")
        energy_table_name = get_output(glue_catalog_dir, "energy_table_name")
        weather_table_name = get_output(glue_catalog_dir, "weather_table_name")
        artefact_bucket_name = get_output(s3_dir, "artefact_bucket_name")
        glue_role_arn = get_output(iam_dir, "glue_role_arn")
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
        deploy_stack(glue_bronze_silver_dir)
        glue_job_name = get_output(glue_bronze_silver_dir, "glue_job_name")
        glue_job_arn = get_output(glue_bronze_silver_dir, "glue_job_arn")
        write_glue_bronze_silver_scheduler_tfvars(
            glue_bronze_silver_scheduler_dir,
            context,
            glue_job_name,
            glue_job_arn,
        )
        deploy_stack(glue_bronze_silver_scheduler_dir)
        write_glue_silver_gold_tfvars(
            glue_silver_gold_dir,
            context,
            kms_key_arn,
            glue_role_arn,
            lakehouse_bucket_name,
            artefact_bucket_name,
        )
        deploy_stack(glue_silver_gold_dir)
        glue_job_name = get_output(glue_silver_gold_dir, "glue_job_name")
        glue_job_arn = get_output(glue_silver_gold_dir, "glue_job_arn")
        write_glue_silver_gold_scheduler_tfvars(
            glue_silver_gold_scheduler_dir,
            context,
            glue_job_name,
            glue_job_arn,
        )
        deploy_stack(glue_silver_gold_scheduler_dir)
        write_model_registry_tfvars(model_registry_dir, context)
        deploy_stack(model_registry_dir)
        write_studio_domain_tfvars(
            studio_domain_dir,
            context,
            kms_key_arn,
            sagemaker_role_arn,
        )
        deploy_stack(studio_domain_dir)
        write_forecast_training_tfvars(
            forecast_training_dir,
            context,
            kms_key_arn,
            artefact_bucket_name,
            lakehouse_bucket_name,
            sagemaker_role_arn,
            get_output(model_registry_dir, "forecast_model_package_group_name"),
        )
        deploy_stack(forecast_training_dir)
        write_anomaly_training_tfvars(
            anomaly_training_dir,
            context,
            kms_key_arn,
            artefact_bucket_name,
            lakehouse_bucket_name,
            sagemaker_role_arn,
            get_output(model_registry_dir, "anomaly_model_package_group_name"),
        )
        deploy_stack(anomaly_training_dir)
        write_forecast_endpoint_tfvars(
            forecast_endpoint_dir,
            context,
            kms_key_arn,
            sagemaker_role_arn,
            get_output(model_registry_dir, "forecast_model_package_group_name"),
        )
        deploy_stack(forecast_endpoint_dir)
        write_anomaly_endpoint_tfvars(
            anomaly_endpoint_dir,
            context,
            kms_key_arn,
            sagemaker_role_arn,
            get_output(model_registry_dir, "anomaly_model_package_group_name"),
        )
        deploy_stack(anomaly_endpoint_dir)
        write_forecast_endpoint_ops_tfvars(
            forecast_endpoint_ops_dir,
            context,
            get_output(forecast_endpoint_dir, "forecast_endpoint_name"),
            get_output(forecast_endpoint_dir, "forecast_endpoint_variant_name"),
        )
        deploy_stack(forecast_endpoint_ops_dir)
        write_model_evaluation_tfvars(
            model_evaluation_dir,
            context,
            kms_key_arn,
            artefact_bucket_name,
            get_output(model_registry_dir, "forecast_model_package_group_name"),
            get_output(model_registry_dir, "anomaly_model_package_group_name"),
        )
        deploy_stack(model_evaluation_dir)
        write_anomaly_endpoint_ops_tfvars(
            anomaly_endpoint_ops_dir,
            context,
            get_output(anomaly_endpoint_dir, "anomaly_endpoint_name"),
            get_output(anomaly_endpoint_dir, "anomaly_endpoint_variant_name"),
        )
        deploy_stack(anomaly_endpoint_ops_dir)
        write_forecast_sarimax_training_tfvars(
            forecast_sarimax_training_dir,
            context,
            kms_key_arn,
            artefact_bucket_name,
            lakehouse_bucket_name,
            sagemaker_role_arn,
            get_output(model_registry_dir, "forecast_model_package_group_name"),
        )
        deploy_stack(forecast_sarimax_training_dir)
        write_forecast_deepar_training_tfvars(
            forecast_deepar_training_dir,
            context,
            kms_key_arn,
            artefact_bucket_name,
            lakehouse_bucket_name,
            sagemaker_role_arn,
            get_output(model_registry_dir, "forecast_model_package_group_name"),
        )
        deploy_stack(forecast_deepar_training_dir)
        write_forecast_tft_training_tfvars(
            forecast_tft_training_dir,
            context,
            kms_key_arn,
            artefact_bucket_name,
            lakehouse_bucket_name,
            sagemaker_role_arn,
            get_output(model_registry_dir, "forecast_model_package_group_name"),
        )
        deploy_stack(forecast_tft_training_dir)
        write_anomaly_residual_training_tfvars(
            anomaly_residual_training_dir,
            context,
            kms_key_arn,
            artefact_bucket_name,
            lakehouse_bucket_name,
            sagemaker_role_arn,
            get_output(model_registry_dir, "anomaly_model_package_group_name"),
        )
        deploy_stack(anomaly_residual_training_dir)
        write_anomaly_one_class_svm_training_tfvars(
            anomaly_one_class_svm_training_dir,
            context,
            kms_key_arn,
            artefact_bucket_name,
            lakehouse_bucket_name,
            sagemaker_role_arn,
            get_output(model_registry_dir, "anomaly_model_package_group_name"),
        )
        deploy_stack(anomaly_one_class_svm_training_dir)
        write_anomaly_autoencoder_training_tfvars(
            anomaly_autoencoder_training_dir,
            context,
            kms_key_arn,
            artefact_bucket_name,
            lakehouse_bucket_name,
            sagemaker_role_arn,
            get_output(model_registry_dir, "anomaly_model_package_group_name"),
        )
        deploy_stack(anomaly_autoencoder_training_dir)

    except subprocess.CalledProcessError as exc:
        print(f"Command failed: {exc}")
        sys.exit(exc.returncode)
