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
 - Full destroy removes resources in this order:

    1. Glue catalogue
    2. EventBridge Scheduler
    3. Lambda ingestion
    4. IAM foundation
    5. S3 lakehouse
    6. KMS
    7. Project context
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
