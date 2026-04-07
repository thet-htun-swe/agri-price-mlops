from __future__ import annotations

from datetime import datetime
from typing import Any
import uuid


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
    response_json: Any,
    fetched_at: datetime,
) -> dict[str, Any]:
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
