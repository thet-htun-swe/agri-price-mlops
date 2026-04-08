import json
import logging
import os
import uuid
from datetime import datetime, timezone

import boto3
import requests

s3_client = boto3.client("s3")
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

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


def build_price_object_key(product_id: str, fetched_at: datetime) -> str:
    year = fetched_at.strftime("%Y")
    month = fetched_at.strftime("%m")
    day = fetched_at.strftime("%d")
    timestamp = fetched_at.strftime("%Y%m%dT%H%M%SZ")
    unique_id = str(uuid.uuid4())

    return (
        "source=price/"
        f"year={year}/month={month}/day={day}/"
        f"product_id={product_id}/"
        f"price-{product_id}-{timestamp}-{unique_id}.json"
    )


def build_price_payload(
    *,
    project_name: str,
    environment_name: str,
    api_url: str,
    product_id: str,
    from_date: str,
    to_date: str,
    status_code: int,
    response_json: dict,
    fetched_at: datetime,
) -> dict:
    return {
        "project": project_name,
        "environment": environment_name,
        "source": "price",
        "fetched_at_utc": fetched_at.isoformat(),
        "request": {
            "url": api_url,
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


def resolve_date_window() -> tuple[str, str]:
    today = datetime.now(timezone.utc).date().isoformat()
    return today, today


def resolve_product_ids() -> list[str]:
    if DEFAULT_PRODUCT_IDS:
        return DEFAULT_PRODUCT_IDS

    raise ValueError("No product IDs provided in PRODUCT_IDS environment variable")


def lambda_handler(event, context):
    try:
        from_date, to_date = resolve_date_window()
        product_ids = resolve_product_ids()
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

            payload = build_price_payload(
                project_name=PROJECT_NAME,
                environment_name=ENV_NAME,
                api_url=PRICE_API_URL,
                product_id=product_id,
                from_date=from_date,
                to_date=to_date,
                status_code=status_code,
                response_json=response_json,
                fetched_at=fetched_at,
            )

            s3_key = build_price_object_key(
                product_id=product_id,
                fetched_at=fetched_at,
            )

            save_json_to_s3(
                bucket_name=RAW_BUCKET,
                key=s3_key,
                payload=payload,
            )

            logger.info(
                json.dumps(
                    {
                        "message": "price_ingestion_saved",
                        "request_date": from_date,
                        "status_code": status_code,
                        "s3_key": s3_key,
                        "product_id": product_id,
                    },
                    ensure_ascii=False,
                )
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
            logger.exception(
                json.dumps(
                    {
                        "message": "price_ingestion_failed",
                        "request_date": from_date,
                        "product_id": product_id,
                        "error": str(exc),
                    },
                    ensure_ascii=False,
                )
            )
            failed.append(
                {
                    "product_id": product_id,
                    "error": str(exc),
                    "status": "failed",
                }
            )
        except Exception as exc:
            logger.exception(
                json.dumps(
                    {
                        "message": "price_ingestion_failed",
                        "request_date": from_date,
                        "product_id": product_id,
                        "error": str(exc),
                    },
                    ensure_ascii=False,
                )
            )
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
