from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from scripts.backfill_common import iter_monthly_windows, write_payload_to_local_path
from services.ingestion_common.price_contract import build_price_object_key, build_price_payload
from services.ingestion_common.weather_contract import build_weather_object_key, build_weather_payload


def test_iter_monthly_windows_splits_full_range_cleanly() -> None:
    windows = list(iter_monthly_windows("2022-01-15", "2022-03-02"))

    assert [(window.start_date, window.end_date) for window in windows] == [
        ("2022-01-15", "2022-01-31"),
        ("2022-02-01", "2022-02-28"),
        ("2022-03-01", "2022-03-02"),
    ]


def test_price_backfill_contract_writes_lambda_compatible_payload(tmp_path: Path) -> None:
    fetched_at = datetime(2026, 4, 7, 12, 30, tzinfo=timezone.utc)
    payload = build_price_payload(
        project_name="agri-price",
        environment_name="dev",
        api_url="https://example.test/prices",
        product_id="P11001",
        from_date="2022-01-01",
        to_date="2022-01-31",
        status_code=200,
        response_json={"product_id": "P11001", "price_list": []},
        fetched_at=fetched_at,
    )

    object_key = build_price_object_key(product_id="P11001", fetched_at=fetched_at)
    written_path = write_payload_to_local_path(tmp_path, object_key, payload)
    saved = json.loads(written_path.read_text(encoding="utf-8"))

    assert "source=price" in written_path.as_posix()
    assert "product_id=P11001" in written_path.as_posix()
    assert saved["source"] == "price"
    assert saved["request"]["params"]["from_date"] == "2022-01-01"
    assert saved["request"]["params"]["to_date"] == "2022-01-31"


def test_weather_backfill_contract_writes_lambda_compatible_payload(tmp_path: Path) -> None:
    fetched_at = datetime(2026, 4, 7, 12, 30, tzinfo=timezone.utc)
    payload = build_weather_payload(
        project_name="agri-price",
        environment_name="dev",
        request_url="https://example.test/weather?start_date=2022-01-01",
        query_params={
            "latitude": "13.7563",
            "longitude": "100.5018",
            "start_date": "2022-01-01",
            "end_date": "2022-01-31",
            "daily": "temperature_2m_mean,precipitation_sum,relative_humidity_2m_mean",
            "timezone": "Asia/Bangkok",
        },
        status_code=200,
        response_text=json.dumps(
            {
                "daily": {
                    "time": ["2022-01-01"],
                    "temperature_2m_mean": [30.0],
                    "precipitation_sum": [0.0],
                    "relative_humidity_2m_mean": [70.0],
                }
            }
        ),
        fetched_at=fetched_at,
    )

    object_key = build_weather_object_key(fetched_at=fetched_at)
    written_path = write_payload_to_local_path(tmp_path, object_key, payload)
    saved = json.loads(written_path.read_text(encoding="utf-8"))

    assert "source=weather" in written_path.as_posix()
    assert saved["source"] == "weather"
    assert saved["query_params"]["start_date"] == "2022-01-01"
    assert "daily" in saved["raw_response"]
