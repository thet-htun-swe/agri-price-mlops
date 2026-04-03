import json
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import boto3
import requests


s3_client = boto3.client("s3")

RAW_BUCKET = os.environ["RAW_BUCKET"]
PROJECT_NAME = os.environ.get("PROJECT_NAME", "agri-price")
ENV_NAME = os.environ.get("ENV_NAME", "dev")
PRICE_API_URL = os.environ.get(
    "PRICE_API_URL",
    "https://dataapi.moc.go.th/gis-product-prices",
)
PRICE_API_TIMEOUT = int(os.environ.get("PRICE_API_TIMEOUT", "60"))
DEFAULT_PRODUCT_IDS = [
    product_id.strip()
    for product_id in os.environ.get("PRODUCT_IDS", "").split(",")
    if product_id.strip()
]
DEFAULT_LOOKBACK_DAYS = int(os.environ.get("PRICE_LOOKBACK_DAYS", "1"))


def build_s3_key(source_name: str, product_id: str, fetched_at: datetime) -> str:
    year = fetched_at.strftime("%Y")
    month = fetched_at.strftime("%m")
    day = fetched_at.strftime("%d")
    timestamp = fetched_at.strftime("%Y%m%dT%H%M%SZ")
    unique_id = str(uuid.uuid4())

    return (
        f"source={source_name}/"
        f"year={year}/month={month}/day={day}/"
        f"product_id={product_id}/"
        f"{source_name}-{product_id}-{timestamp}-{unique_id}.json"
    )


def build_payload(
    product_id: str,
    from_date: str,
    to_date: str,
    status_code: int,
    response_json: Any,
    fetched_at: datetime,
) -> dict:
    return {
        "project": PROJECT_NAME,
        "environment": ENV_NAME,
        "source": "price",
        "fetched_at_utc": fetched_at.isoformat(),
        "request": {
            "url": PRICE_API_URL,
            "params": {
                "product_id": product_id,
                "from_date": from_date,
                "to_date": to_date,
            },
        },
        "http_status_code": status_code,
        "raw_response": response_json,
    }


def save_json_to_s3(bucket_name: str, key: str, payload: dict) -> None:
    s3_client.put_object(
        Bucket=bucket_name,
        Key=key,
        Body=json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8"),
        ContentType="application/json",
    )


def fetch_product_price(product_id: str, from_date: str, to_date: str):
    response = requests.get(
        PRICE_API_URL,
        params={
            "product_id": product_id,
            "from_date": from_date,
            "to_date": to_date,
        },
        timeout=PRICE_API_TIMEOUT,
    )
    response.raise_for_status()
    return response.status_code, response.json()


def parse_event_time(event: dict) -> datetime | None:
    event_time = event.get("time")
    if not event_time:
        return None

    normalized_time = event_time.replace("Z", "+00:00")
    return datetime.fromisoformat(normalized_time).astimezone(timezone.utc)


def resolve_date_window(event: dict) -> tuple[str, str]:
    from_date = event.get("from_date")
    to_date = event.get("to_date")

    if from_date and to_date:
        return from_date, to_date

    if from_date or to_date:
        raise ValueError("Provide both from_date and to_date, or omit both")

    scheduled_at = parse_event_time(event) or datetime.now(timezone.utc)
    target_day = (scheduled_at.date() - timedelta(days=DEFAULT_LOOKBACK_DAYS)).isoformat()
    return target_day, target_day


def resolve_product_ids(event: dict) -> list[str]:
    single_product_id = event.get("product_id")
    multiple_product_ids = event.get("product_ids")

    if single_product_id and multiple_product_ids:
        raise ValueError("Provide either product_id or product_ids, not both")

    if single_product_id:
        return [single_product_id]

    if multiple_product_ids:
        return [product_id.strip() for product_id in multiple_product_ids if product_id.strip()]

    if DEFAULT_PRODUCT_IDS:
        return DEFAULT_PRODUCT_IDS

    raise ValueError("No product IDs provided in event or PRODUCT_IDS environment variable")


def lambda_handler(event, context):
    event = event or {}

    try:
        from_date, to_date = resolve_date_window(event)
    except ValueError as exc:
        return {
            "statusCode": 400,
            "body": json.dumps({"message": str(exc)}),
        }

    try:
        product_ids = resolve_product_ids(event)
    except ValueError as exc:
        return {
            "statusCode": 400,
            "body": json.dumps({"message": str(exc)}),
        }

    results = []
    failed = []

    for product_id in product_ids:
        fetched_at = datetime.now(timezone.utc)

        try:
            status_code, response_json = fetch_product_price(
                product_id=product_id,
                from_date=from_date,
                to_date=to_date,
            )

            payload = build_payload(
                product_id=product_id,
                from_date=from_date,
                to_date=to_date,
                status_code=status_code,
                response_json=response_json,
                fetched_at=fetched_at,
            )

            s3_key = build_s3_key(
                source_name="price",
                product_id=product_id,
                fetched_at=fetched_at,
            )

            save_json_to_s3(
                bucket_name=RAW_BUCKET,
                key=s3_key,
                payload=payload,
            )

            results.append(
                {
                    "product_id": product_id,
                    "bucket": RAW_BUCKET,
                    "key": s3_key,
                    "status": "saved",
                }
            )

        except requests.RequestException as exc:
            failed.append(
                {
                    "product_id": product_id,
                    "error": str(exc),
                    "status": "failed",
                }
            )
        except Exception as exc:
            failed.append(
                {
                    "product_id": product_id,
                    "error": str(exc),
                    "status": "failed",
                }
            )

    return {
        "statusCode": 200 if not failed else 207,
        "body": json.dumps(
            {
                "message": "Price ingestion completed",
                "successful_count": len(results),
                "failed_count": len(failed),
                "results": results,
                "failed": failed,
            },
            ensure_ascii=False,
        ),
    }
