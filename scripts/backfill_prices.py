from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from requests import Response


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.backfill_common import iter_monthly_windows, write_payload_to_local_path
from services.ingestion_common.price_contract import build_price_object_key, build_price_payload


DEFAULT_PRICE_API_URL = "https://dataapi.moc.go.th/gis-product-prices"
DEFAULT_RETRY_TOTAL = 3
DEFAULT_RETRY_BACKOFF_SECONDS = 2.0
DEFAULT_REQUEST_HEADERS = {
    "Accept": "application/json",
    "User-Agent": "Mozilla/5.0",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Backfill historical raw price payloads to the local raw zone using the Lambda-compatible schema."
    )
    parser.add_argument("--product-ids", required=True, help="Comma-separated product IDs to collect.")
    parser.add_argument("--start-date", required=True, help="Inclusive start date in YYYY-MM-DD format.")
    parser.add_argument("--end-date", required=True, help="Inclusive end date in YYYY-MM-DD format.")
    parser.add_argument("--output-root", default="data/raw/price", help="Root directory for raw price payload files.")
    parser.add_argument("--project-name", default="agri-price", help="Project name stored in each raw payload.")
    parser.add_argument("--environment-name", default="dev", help="Environment name stored in each raw payload.")
    parser.add_argument("--api-url", default=DEFAULT_PRICE_API_URL, help="Price API base URL.")
    parser.add_argument("--timeout", type=int, default=60, help="Price API request timeout in seconds.")
    parser.add_argument(
        "--retry-total",
        type=int,
        default=DEFAULT_RETRY_TOTAL,
        help="Number of retry attempts for transient API failures.",
    )
    parser.add_argument(
        "--retry-backoff-seconds",
        type=float,
        default=DEFAULT_RETRY_BACKOFF_SECONDS,
        help="Base backoff delay between retry attempts.",
    )
    parser.add_argument("--sleep-seconds", type=float, default=0.0, help="Optional delay between requests.")
    return parser


def resolve_product_ids(raw_value: str) -> list[str]:
    product_ids = [product_id.strip() for product_id in raw_value.split(",") if product_id.strip()]
    if not product_ids:
        raise ValueError("At least one product ID is required.")
    return product_ids


def build_api_error(response: Response) -> requests.HTTPError:
    response_excerpt = response.text[:500]
    return requests.HTTPError(
        f"{response.status_code} error for {response.url}: {response_excerpt}",
        response=response,
    )


def fetch_price_payload(
    api_url: str,
    product_id: str,
    start_date: str,
    end_date: str,
    timeout: int,
    retry_total: int,
    retry_backoff_seconds: float,
) -> tuple[int, dict]:
    params = {
        "product_id": product_id,
        "from_date": start_date,
        "to_date": end_date,
    }
    last_error: Exception | None = None

    for attempt in range(1, retry_total + 1):
        try:
            response = requests.get(
                api_url,
                params=params,
                headers=DEFAULT_REQUEST_HEADERS,
                timeout=timeout,
            )
            if response.status_code >= 400:
                raise build_api_error(response)
            return response.status_code, response.json()
        except (requests.Timeout, requests.ConnectionError, requests.HTTPError) as exc:
            last_error = exc
            should_retry = False
            if isinstance(exc, requests.HTTPError) and exc.response is not None:
                should_retry = exc.response.status_code in {500, 502, 503, 504}
            elif isinstance(exc, (requests.Timeout, requests.ConnectionError)):
                should_retry = True

            if attempt >= retry_total or not should_retry:
                raise

            time.sleep(retry_backoff_seconds * attempt)

    if last_error is not None:
        raise last_error
    raise RuntimeError("Unexpected retry loop exit without a result.")


def main() -> int:
    args = build_parser().parse_args()
    product_ids = resolve_product_ids(args.product_ids)

    files_written = 0
    windows_processed = 0

    for window in iter_monthly_windows(args.start_date, args.end_date):
        for product_id in product_ids:
            fetched_at = datetime.now(timezone.utc)
            status_code, response_json = fetch_price_payload(
                api_url=args.api_url,
                product_id=product_id,
                start_date=window.start_date,
                end_date=window.end_date,
                timeout=args.timeout,
                retry_total=args.retry_total,
                retry_backoff_seconds=args.retry_backoff_seconds,
            )
            payload = build_price_payload(
                project_name=args.project_name,
                environment_name=args.environment_name,
                api_url=args.api_url,
                product_id=product_id,
                from_date=window.start_date,
                to_date=window.end_date,
                status_code=status_code,
                response_json=response_json,
                fetched_at=fetched_at,
            )
            object_key = build_price_object_key(product_id=product_id, fetched_at=fetched_at)
            write_payload_to_local_path(args.output_root, object_key, payload)

            files_written += 1
            windows_processed += 1
            if args.sleep_seconds > 0:
                time.sleep(args.sleep_seconds)

    print(
        json.dumps(
            {
                "output_root": str(Path(args.output_root).resolve()),
                "product_ids": product_ids,
                "start_date": args.start_date,
                "end_date": args.end_date,
                "windowing": "monthly",
                "request_count": windows_processed,
                "files_written": files_written,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
