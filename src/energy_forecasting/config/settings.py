"""Shared runtime settings for the energy forecasting project.

This module centralises environment-driven configuration so that the rest of
the codebase can read a single typed settings object rather than repeatedly
querying `os.environ` throughout the application.

Examples
--------
>>> settings = Settings.from_env()
>>> settings.environment in {"dev", "prod"}
True
"""

from dataclasses import dataclass
import os


@dataclass(frozen=True)
class Settings:
    """
    Runtime configuration loaded from environment variables.

    Attributes
    ----------
    project_name : str
        Human-readable project name used in logs and metadata.
    environment : str
        Deployment environment such as `dev` or `prod`.
    aws_region : str
        AWS region in which the workload is expected to run.
    lakehouse_bucket : str
        S3 bucket storing Bronze, Silver, and Gold data.
    artefact_bucket : str
        S3 bucket storing model artefacts and related outputs.
    monitoring_bucket : str
        S3 bucket storing monitoring and diagnostics outputs.
    """

    project_name: str
    environment: str
    aws_region: str
    lakehouse_bucket: str
    artefact_bucket: str
    monitoring_bucket: str

    @classmethod
    def from_env(cls) -> "Settings":
        """
        Create a settings object from environment variables.

        Returns
        -------
        Settings
            Settings instance populated from the current shell environment.

        Notes
        -----
        - Defaults are intentionally conservative so the local development
          workflow remains usable before every infrastructure value exists.
        - Bucket names default to empty strings because they are deployment
          outputs rather than hardcoded application constants.

        Examples
        --------
        >>> settings = Settings.from_env()
        >>> settings.aws_region
        'eu-west-2'
        """

        return cls(
            project_name=os.getenv(
                "PROJECT_NAME",
                "Real-Time Energy Forecasting and Anomaly Detection",
            ),
            environment=os.getenv("PROJECT_ENV", "dev"),
            aws_region=os.getenv("AWS_REGION", "eu-west-2"),
            lakehouse_bucket=os.getenv("LAKEHOUSE_BUCKET", ""),
            artefact_bucket=os.getenv("ARTEFACT_BUCKET", ""),
            monitoring_bucket=os.getenv("MONITORING_BUCKET", ""),
        )
