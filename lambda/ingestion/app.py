"""Starter ingestion Lambda for Bronze manifest landing.

The function in this module does not yet fetch the upstream APIs directly.
Instead, it records a lightweight ingestion manifest into the Bronze layer so
that the infrastructure, IAM, packaging, and S3 write path can be verified
early in the project.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from urllib.parse import quote_plus

import boto3


def _build_manifest(event: dict, context: object) -> dict[str, object]:
    """
    Build a manifest describing a single ingestion invocation.

    Parameters
    ----------
    event : dict
        Lambda invocation event payload.
    context : object
        Lambda context object supplied by the runtime.

    Returns
    -------
    dict[str, object]
        Serializable manifest capturing timing, deployment metadata, source
        configuration, and the original event payload.
    """

    timestamp = datetime.now(timezone.utc)
    request_id = getattr(context, "aws_request_id", "manual-invoke")

    return {
        "request_id": request_id,
        "event_time_utc": timestamp.isoformat(),
        "deployment_name": os.environ["DEPLOYMENT_NAME"],
        "environment": os.environ["PROJECT_ENV"],
        "sources": {
            "energy_api_base_url": os.environ["ENERGY_API_BASE_URL"],
            "weather_api_base_url": os.environ["WEATHER_API_BASE_URL"],
        },
        "event": event,
    }


def _build_s3_key(prefix: str, request_id: str, event_time_utc: str) -> str:
    """
    Build the S3 object key used to store an ingestion manifest.

    Parameters
    ----------
    prefix : str
        Base S3 prefix for manifest objects.
    request_id : str
        Lambda request identifier.
    event_time_utc : str
        UTC timestamp string for the invocation.

    Returns
    -------
    str
        S3 key partitioned by date and suffixed by request identifier.
    """

    date_key = event_time_utc[:10]
    safe_request_id = quote_plus(request_id)
    normalized_prefix = prefix.strip("/")
    return f"{normalized_prefix}/dt={date_key}/{safe_request_id}.json"


def handler(event: dict, context: object) -> dict[str, object]:
    """
    Persist a lightweight ingestion manifest into the Bronze lakehouse.

    Parameters
    ----------
    event : dict
        Lambda invocation event payload.
    context : object
        Lambda context object supplied by the runtime.

    Returns
    -------
    dict[str, object]
        Response containing the S3 location written by the function.

    Notes
    -----
    The manifest is intentionally simple. Its main purpose is to prove that
    packaging, IAM, encryption, and Bronze writes are correctly wired before
    the project adds richer API-fetching logic.
    """

    manifest = _build_manifest(event, context)
    s3_key = _build_s3_key(
        prefix=os.environ["BRONZE_INGEST_PREFIX"],
        request_id=manifest["request_id"],
        event_time_utc=manifest["event_time_utc"],
    )

    # Write a single manifest object so the platform has an auditable record
    # of what the ingestion trigger attempted to do.
    boto3.client("s3").put_object(
        Bucket=os.environ["LAKEHOUSE_BUCKET"],
        Key=s3_key,
        Body=json.dumps(manifest, indent=2).encode("utf-8"),
        ContentType="application/json",
        ServerSideEncryption="aws:kms",
        SSEKMSKeyId=os.environ["KMS_KEY_ARN"],
    )

    return {
        "statusCode": 200,
        "bucket": os.environ["LAKEHOUSE_BUCKET"],
        "key": s3_key,
    }
