"""Log a small smoke-test run to the managed SageMaker MLflow tracking server.

Examples
--------
After deploying the tracking server:

>>> # uv run --extra mlflow python scripts/run_mlflow_tracking_smoke.py
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

try:
    import mlflow
    import sagemaker_mlflow  # noqa: F401
except ModuleNotFoundError as exc:  # pragma: no cover - environment guard
    raise SystemExit(
        "MLflow smoke logging requires the optional MLflow dependencies. "
        "Install them with `uv sync --extra mlflow` and rerun via "
        "`uv run --extra mlflow python scripts/run_mlflow_tracking_smoke.py`."
    ) from exc


def run_capture_optional(cmd: list[str]) -> str | None:
    """Execute a command and return its stripped stdout, or `None` on failure."""

    try:
        return subprocess.check_output(cmd, text=True).strip()
    except subprocess.CalledProcessError:
        return None


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
    if output:
        return output

    value = get_output_from_state(tf_dir, output_name)
    if value is None:
        raise RuntimeError(
            f"Terraform output '{output_name}' was not found in {tf_dir}. "
            "Reapply the module first, for example `python scripts\\deploy.py --mlflow-tracking-only`."
        )
    return value


def build_parser() -> argparse.ArgumentParser:
    """Create the CLI parser."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--experiment-name",
        default=None,
        help="Optional explicit MLflow experiment name. Defaults to '<tracking-server-name>-smoke'.",
    )
    parser.add_argument(
        "--run-name",
        default=None,
        help="Optional explicit MLflow run name. Defaults to a UTC timestamped smoke-run name.",
    )
    return parser


def main() -> None:
    """Log a small verification run to the managed SageMaker MLflow tracking server."""

    load_env_file(REPO_ROOT / ".env")
    args = build_parser().parse_args()
    tracking_dir = REPO_ROOT / "terraform" / "29_sagemaker_mlflow_tracking"

    tracking_server_arn = get_output(tracking_dir, "mlflow_tracking_server_arn")
    tracking_server_name = get_output(tracking_dir, "mlflow_tracking_server_name")
    tracking_server_url = get_output(tracking_dir, "mlflow_tracking_server_url")
    artifact_store_uri = get_output(tracking_dir, "mlflow_tracking_server_artifact_store_uri")

    experiment_name = args.experiment_name or f"{tracking_server_name}-smoke"
    run_name = args.run_name or f"smoke-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"

    mlflow.set_tracking_uri(tracking_server_arn)
    mlflow.set_experiment(experiment_name)

    with tempfile.TemporaryDirectory() as temp_dir:
        note_path = Path(temp_dir) / "mlflow-smoke-note.txt"
        note_path.write_text(
            (
                f"tracking_server_name={tracking_server_name}\n"
                f"tracking_server_arn={tracking_server_arn}\n"
                f"tracking_server_url={tracking_server_url}\n"
                f"artifact_store_uri={artifact_store_uri}\n"
            ),
            encoding="utf-8",
        )

        with mlflow.start_run(run_name=run_name):
            mlflow.log_param("tracking_server_name", tracking_server_name)
            mlflow.log_param("tracking_server_url", tracking_server_url)
            mlflow.log_metric("smoke_metric", 1.0)
            mlflow.set_tag("deployment_check", "true")
            mlflow.log_artifact(str(note_path))

    print("MLflow smoke run logged successfully.")
    print(f"Tracking server: {tracking_server_name}")
    print(f"Tracking URI: {tracking_server_arn}")
    print(f"Experiment: {experiment_name}")
    print(f"Run name: {run_name}")


if __name__ == "__main__":
    main()
