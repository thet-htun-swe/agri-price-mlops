import json
import logging
import os
import uuid
from datetime import datetime, timezone
from urllib.parse import urlencode

import boto3
import requests

s3_client = boto3.client("s3")
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

RAW_BUCKET = os.environ["RAW_BUCKET"]
PROJECT_NAME = os.environ.get("PROJECT_NAME", "agri-price")
ENV_NAME = os.environ.get("ENV_NAME", "dev")
WEATHER_API_URL = os.environ.get("WEATHER_API_URL", "https://archive-api.open-meteo.com/v1/archive")
WEATHER_API_TIMEOUT = int(os.environ.get("WEATHER_API_TIMEOUT", "30"))


def build_weather_object_key(fetched_at: datetime) -> str:
    year = fetched_at.strftime("%Y")
    month = fetched_at.strftime("%m")
    day = fetched_at.strftime("%d")
    unique_id = str(uuid.uuid4())

    return (
        "source=weather/"
        f"year={year}/month={month}/day={day}/"
        f"weather-{fetched_at.strftime('%Y%m%dT%H%M%SZ')}-{unique_id}.json"
    )


def build_weather_payload(
    *,
    project_name: str,
    environment_name: str,
    request_url: str,
    query_params: dict[str, str],
    status_code: int,
    response_text: str,
    fetched_at: datetime,
) -> dict:
    return {
        "project": project_name,
        "environment": environment_name,
        "source": "weather",
        "fetched_at_utc": fetched_at.isoformat(),
        "request_url": request_url,
        "query_params": query_params,
        "http_status_code": status_code,
        "raw_response": json.loads(response_text),
    }


def save_to_s3(bucket_name: str, key: str, payload: dict) -> None:
    s3_client.put_object(
        Bucket=bucket_name,
        Key=key,
        Body=json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8"),
        ContentType="application/json",
    )


def resolve_date_window() -> tuple[str, str]:
    today = datetime.now(timezone.utc).date().isoformat()
    return today, today


def lambda_handler(event, context):
    try:
        start_date, end_date = resolve_date_window()
    except ValueError as exc:
        return {
            "statusCode": 400,
            "body": json.dumps({"message": str(exc)}),
        }

    # Bangkok coordinates as default example
    default_params = {
        "latitude": "13.7563",
        "longitude": "100.5018",
        "start_date": start_date,
        "end_date": end_date,
        "daily": "temperature_2m_mean,precipitation_sum,relative_humidity_2m_mean",
        "timezone": "Asia/Bangkok",
    }

    merged_params = default_params
    encoded_params = urlencode(merged_params)
    request_url = f"{WEATHER_API_URL}?{encoded_params}"

    fetched_at = datetime.now(timezone.utc)

    try:
        response = requests.get(
            WEATHER_API_URL,
            params=merged_params,
            timeout=WEATHER_API_TIMEOUT,
        )
        response.raise_for_status()

        payload = build_weather_payload(
            project_name=PROJECT_NAME,
            environment_name=ENV_NAME,
            request_url=request_url,
            query_params=merged_params,
            status_code=response.status_code,
            response_text=response.text,
            fetched_at=fetched_at,
        )

        s3_key = build_weather_object_key(fetched_at=fetched_at)
        save_to_s3(bucket_name=RAW_BUCKET, key=s3_key, payload=payload)

        logger.info(
            json.dumps(
                {
                    "message": "weather_ingestion_saved",
                    "request_date": start_date,
                    "status_code": response.status_code,
                    "s3_key": s3_key,
                },
                ensure_ascii=False,
            )
        )

        return {
            "statusCode": 200,
            "body": json.dumps(
                {
                    "message": "Weather raw data saved successfully",
                    "bucket": RAW_BUCKET,
                    "key": s3_key,
                }
            ),
        }

    except requests.RequestException as exc:
        logger.exception(
            json.dumps(
                {
                    "message": "weather_ingestion_failed",
                    "request_date": start_date,
                    "error": str(exc),
                    "request_url": request_url,
                },
                ensure_ascii=False,
            )
        )
        return {
            "statusCode": 500,
            "body": json.dumps(
                {
                    "message": "Failed to fetch weather data",
                    "error": str(exc),
                    "request_url": request_url,
                }
            ),
        }
