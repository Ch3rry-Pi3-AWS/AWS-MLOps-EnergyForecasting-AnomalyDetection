"""Ingestion Lambda for landing public energy and weather data in Bronze.

This module performs the first real external data collection step in the
project. On each invocation, it fetches:

- electricity demand data from Elexon's public Insights API
- weather forecast data from Open-Meteo

The raw JSON payloads are written into the Bronze layer of the lakehouse and
an ingestion manifest is written alongside them so each invocation is
auditable.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote_plus, urlencode
from urllib.request import Request, urlopen

HTTP_TIMEOUT_SECONDS = 30
JSON_CONTENT_TYPE = "application/json"


def _utc_now() -> datetime:
    """
    Return the current UTC timestamp as a timezone-aware datetime.

    Returns
    -------
    datetime
        Current UTC timestamp.
    """

    return datetime.now(timezone.utc)


def _join_url(base_url: str, path: str) -> str:
    """
    Join a base URL and relative path without duplicating slashes.

    Parameters
    ----------
    base_url : str
        API base URL, for example `https://data.elexon.co.uk`.
    path : str
        Relative API path, for example `/bmrs/api/v1/datasets/ITSDO`.

    Returns
    -------
    str
        Combined URL.
    """

    return f"{base_url.rstrip('/')}/{path.lstrip('/')}"


def _fetch_json(url: str, headers: dict[str, str] | None = None) -> dict[str, Any]:
    """
    Perform an HTTP GET request and decode the JSON response.

    Parameters
    ----------
    url : str
        Fully qualified request URL.
    headers : dict[str, str] | None
        Optional request headers.

    Returns
    -------
    dict[str, Any]
        Parsed JSON payload returned by the upstream API.
    """

    request = Request(url=url, headers=headers or {}, method="GET")
    with urlopen(request, timeout=HTTP_TIMEOUT_SECONDS) as response:
        return json.loads(response.read().decode("utf-8"))


def _build_partitioned_s3_key(prefix: str, source_name: str, request_id: str, event_time_utc: str) -> str:
    """
    Build a deterministic S3 object key for raw source payloads or manifests.

    Parameters
    ----------
    prefix : str
        Base S3 prefix under which objects should be written.
    source_name : str
        Logical source identifier such as `energy`, `weather`, or `manifest`.
    request_id : str
        Lambda request identifier.
    event_time_utc : str
        UTC timestamp string for the invocation.

    Returns
    -------
    str
        Partitioned S3 key in the form `<prefix>/<source>/dt=<date>/<request>.json`.
    """

    date_key = event_time_utc[:10]
    safe_request_id = quote_plus(request_id)
    normalized_prefix = prefix.strip("/")
    normalized_source = source_name.strip("/")
    return f"{normalized_prefix}/{normalized_source}/dt={date_key}/{safe_request_id}.json"


def _put_json_to_s3(
    s3_client: Any,
    bucket_name: str,
    key: str,
    payload: dict[str, Any],
    kms_key_arn: str,
) -> None:
    """
    Persist a JSON payload into S3 using KMS-backed server-side encryption.

    Parameters
    ----------
    s3_client : Any
        Boto3 S3 client.
    bucket_name : str
        Destination S3 bucket.
    key : str
        Destination object key.
    payload : dict[str, Any]
        Serializable JSON payload to store.
    kms_key_arn : str
        KMS key ARN used for encryption.
    """

    s3_client.put_object(
        Bucket=bucket_name,
        Key=key,
        Body=json.dumps(payload, indent=2).encode("utf-8"),
        ContentType=JSON_CONTENT_TYPE,
        ServerSideEncryption="aws:kms",
        SSEKMSKeyId=kms_key_arn,
    )


def _fetch_energy_payload() -> dict[str, Any]:
    """
    Fetch the latest public electricity demand payload from Elexon.

    Returns
    -------
    dict[str, Any]
        JSON payload returned by the Elexon demand endpoint.
    """

    energy_url = _join_url(
        base_url=os.environ["ENERGY_API_BASE_URL"],
        path=os.environ["ENERGY_API_PATH"],
    )
    return _fetch_json(
        url=energy_url,
        headers={"Accept": JSON_CONTENT_TYPE},
    )


def _fetch_weather_payload() -> dict[str, Any]:
    """
    Fetch the configured public weather payload from Open-Meteo.

    Returns
    -------
    dict[str, Any]
        JSON payload returned by the weather endpoint.
    """

    weather_url = _join_url(
        base_url=os.environ["WEATHER_API_BASE_URL"],
        path=os.environ["WEATHER_API_PATH"],
    )
    query_string = urlencode(
        {
            "latitude": os.environ["WEATHER_LATITUDE"],
            "longitude": os.environ["WEATHER_LONGITUDE"],
            "hourly": os.environ["WEATHER_HOURLY_FIELDS"],
            "timezone": os.environ["WEATHER_TIMEZONE"],
        }
    )
    return _fetch_json(url=f"{weather_url}?{query_string}")


def _build_source_record(source_name: str, key: str, payload: dict[str, Any]) -> dict[str, Any]:
    """
    Build a concise manifest record for a stored source payload.

    Parameters
    ----------
    source_name : str
        Logical source identifier.
    key : str
        S3 key used to store the raw payload.
    payload : dict[str, Any]
        Raw payload returned by the upstream API.

    Returns
    -------
    dict[str, Any]
        Manifest record describing the stored source object.
    """

    record_count = len(payload.get("data", [])) if isinstance(payload.get("data"), list) else None
    return {
        "source_name": source_name,
        "s3_key": key,
        "record_count": record_count,
    }


def _build_manifest_base(event: dict[str, Any], context: object, event_time_utc: str) -> dict[str, Any]:
    """
    Build the base ingestion manifest shared by both success and failure paths.

    Parameters
    ----------
    event : dict[str, Any]
        Lambda invocation event payload.
    context : object
        Lambda context object supplied by the runtime.
    event_time_utc : str
        Invocation timestamp in UTC.

    Returns
    -------
    dict[str, Any]
        Base manifest describing the invocation metadata and configured sources.
    """

    request_id = getattr(context, "aws_request_id", "manual-invoke")
    return {
        "request_id": request_id,
        "event_time_utc": event_time_utc,
        "deployment_name": os.environ["DEPLOYMENT_NAME"],
        "environment": os.environ["PROJECT_ENV"],
        "status": "started",
        "sources": {
            "energy": {
                "base_url": os.environ["ENERGY_API_BASE_URL"],
                "path": os.environ["ENERGY_API_PATH"],
            },
            "weather": {
                "base_url": os.environ["WEATHER_API_BASE_URL"],
                "path": os.environ["WEATHER_API_PATH"],
                "latitude": os.environ["WEATHER_LATITUDE"],
                "longitude": os.environ["WEATHER_LONGITUDE"],
                "hourly_fields": os.environ["WEATHER_HOURLY_FIELDS"],
                "timezone": os.environ["WEATHER_TIMEZONE"],
            },
        },
        "event": event,
        "outputs": {},
    }


def handler(event: dict[str, Any], context: object) -> dict[str, Any]:
    """
    Fetch public source payloads and persist them into the Bronze lakehouse.

    Parameters
    ----------
    event : dict[str, Any]
        Lambda invocation event payload.
    context : object
        Lambda context object supplied by the runtime.

    Returns
    -------
    dict[str, Any]
        Response describing the manifest written for the invocation.

    Notes
    -----
    The function writes three Bronze objects per successful invocation:

    - one raw Elexon payload
    - one raw Open-Meteo payload
    - one manifest describing the invocation and both object locations
    """

    event_time_utc = _utc_now().isoformat()
    request_id = getattr(context, "aws_request_id", "manual-invoke")
    bucket_name = os.environ["LAKEHOUSE_BUCKET"]
    raw_prefix = os.environ["BRONZE_RAW_PREFIX"]
    manifest_prefix = os.environ["BRONZE_INGEST_PREFIX"]
    kms_key_arn = os.environ["KMS_KEY_ARN"]
    # Import boto3 lazily so the module remains importable in lightweight
    # local test environments that do not ship the AWS SDK by default.
    import boto3

    s3_client = boto3.client("s3")

    manifest = _build_manifest_base(event=event, context=context, event_time_utc=event_time_utc)
    manifest_key = _build_partitioned_s3_key(
        prefix=manifest_prefix,
        source_name="manifest",
        request_id=request_id,
        event_time_utc=event_time_utc,
    )

    try:
        # Fetch the upstream API payloads first so the invocation fails fast if
        # a source is unavailable or returns invalid JSON.
        energy_payload = _fetch_energy_payload()
        weather_payload = _fetch_weather_payload()

        energy_key = _build_partitioned_s3_key(
            prefix=raw_prefix,
            source_name="energy",
            request_id=request_id,
            event_time_utc=event_time_utc,
        )
        weather_key = _build_partitioned_s3_key(
            prefix=raw_prefix,
            source_name="weather",
            request_id=request_id,
            event_time_utc=event_time_utc,
        )

        # Persist the raw payloads before the manifest so the manifest can
        # reference concrete object locations that definitely exist.
        _put_json_to_s3(
            s3_client=s3_client,
            bucket_name=bucket_name,
            key=energy_key,
            payload=energy_payload,
            kms_key_arn=kms_key_arn,
        )
        _put_json_to_s3(
            s3_client=s3_client,
            bucket_name=bucket_name,
            key=weather_key,
            payload=weather_payload,
            kms_key_arn=kms_key_arn,
        )

        manifest["status"] = "success"
        manifest["outputs"] = {
            "energy": _build_source_record("energy", energy_key, energy_payload),
            "weather": _build_source_record("weather", weather_key, weather_payload),
        }

        _put_json_to_s3(
            s3_client=s3_client,
            bucket_name=bucket_name,
            key=manifest_key,
            payload=manifest,
            kms_key_arn=kms_key_arn,
        )
    except Exception as exc:
        # Capture the failure in Bronze as well so operational diagnostics do
        # not rely solely on CloudWatch logs.
        manifest["status"] = "failed"
        manifest["error"] = {
            "type": exc.__class__.__name__,
            "message": str(exc),
        }
        _put_json_to_s3(
            s3_client=s3_client,
            bucket_name=bucket_name,
            key=manifest_key,
            payload=manifest,
            kms_key_arn=kms_key_arn,
        )
        raise

    return {
        "statusCode": 200,
        "bucket": bucket_name,
        "manifest_key": manifest_key,
        "raw_keys": {
            "energy": manifest["outputs"]["energy"]["s3_key"],
            "weather": manifest["outputs"]["weather"]["s3_key"],
        },
    }
