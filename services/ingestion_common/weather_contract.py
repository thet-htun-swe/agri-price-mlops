from __future__ import annotations

from datetime import datetime
from typing import Any
import json
import uuid


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
) -> dict[str, Any]:
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
