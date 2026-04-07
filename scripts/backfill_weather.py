from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode

import requests


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.backfill_common import iter_monthly_windows, write_payload_to_local_path
from services.ingestion_common.weather_contract import build_weather_object_key, build_weather_payload


DEFAULT_WEATHER_API_URL = "https://archive-api.open-meteo.com/v1/archive"
DEFAULT_DAILY_VARIABLES = "temperature_2m_mean,precipitation_sum,relative_humidity_2m_mean"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Backfill historical raw weather payloads to the local raw zone using the Lambda-compatible schema."
    )
    parser.add_argument("--start-date", required=True, help="Inclusive start date in YYYY-MM-DD format.")
    parser.add_argument("--end-date", required=True, help="Inclusive end date in YYYY-MM-DD format.")
    parser.add_argument("--output-root", default="data/raw/weather", help="Root directory for raw weather payload files.")
    parser.add_argument("--project-name", default="agri-price", help="Project name stored in each raw payload.")
    parser.add_argument("--environment-name", default="dev", help="Environment name stored in each raw payload.")
    parser.add_argument("--api-url", default=DEFAULT_WEATHER_API_URL, help="Weather API base URL.")
    parser.add_argument("--timeout", type=int, default=60, help="Weather API request timeout in seconds.")
    parser.add_argument("--sleep-seconds", type=float, default=0.0, help="Optional delay between requests.")
    parser.add_argument("--latitude", default="13.7563", help="Latitude used for weather history requests.")
    parser.add_argument("--longitude", default="100.5018", help="Longitude used for weather history requests.")
    parser.add_argument("--timezone", default="Asia/Bangkok", help="Timezone forwarded to the weather API.")
    parser.add_argument(
        "--daily-variables",
        default=DEFAULT_DAILY_VARIABLES,
        help="Comma-separated daily weather variables expected by Phase B.",
    )
    return parser


def fetch_weather_payload(api_url: str, query_params: dict[str, str], timeout: int) -> tuple[int, str]:
    response = requests.get(api_url, params=query_params, timeout=timeout)
    response.raise_for_status()
    return response.status_code, response.text


def main() -> int:
    args = build_parser().parse_args()
    files_written = 0

    for window in iter_monthly_windows(args.start_date, args.end_date):
        query_params = {
            "latitude": args.latitude,
            "longitude": args.longitude,
            "start_date": window.start_date,
            "end_date": window.end_date,
            "daily": args.daily_variables,
            "timezone": args.timezone,
        }
        fetched_at = datetime.now(timezone.utc)
        status_code, response_text = fetch_weather_payload(
            api_url=args.api_url,
            query_params=query_params,
            timeout=args.timeout,
        )
        request_url = f"{args.api_url}?{urlencode(query_params)}"
        payload = build_weather_payload(
            project_name=args.project_name,
            environment_name=args.environment_name,
            request_url=request_url,
            query_params=query_params,
            status_code=status_code,
            response_text=response_text,
            fetched_at=fetched_at,
        )
        object_key = build_weather_object_key(fetched_at=fetched_at)
        write_payload_to_local_path(args.output_root, object_key, payload)
        files_written += 1

        if args.sleep_seconds > 0:
            time.sleep(args.sleep_seconds)

    print(
        json.dumps(
            {
                "output_root": str(Path(args.output_root).resolve()),
                "start_date": args.start_date,
                "end_date": args.end_date,
                "windowing": "monthly",
                "files_written": files_written,
                "latitude": args.latitude,
                "longitude": args.longitude,
                "timezone": args.timezone,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
