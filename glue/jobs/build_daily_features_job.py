from __future__ import annotations

import argparse
import io
import json
import logging
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import boto3
import pandas as pd


CURRENT_DIR = Path(__file__).resolve().parent
REPO_ROOT = CURRENT_DIR.parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from glue.jobs.phase_b_transform import (
    DatasetBundle,
    MappingTables,
    TransformConfig,
    build_dataset_bundle,
    load_name_mapping_from_csv_bytes,
    write_bundle_to_local,
)


logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def parse_int_list(raw_value: str) -> tuple[int, ...]:
    return tuple(int(part.strip()) for part in raw_value.split(",") if part.strip())


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Glue Phase B job for clean and feature datasets.")
    parser.add_argument("--raw-bucket", required=True, help="S3 bucket containing raw price and weather data.")
    parser.add_argument("--price-prefix", required=True, help="S3 prefix for raw price JSON files.")
    parser.add_argument("--weather-prefix", required=True, help="S3 prefix for raw weather JSON files.")
    parser.add_argument(
        "--processed-bucket",
        required=True,
        help="S3 bucket where clean_prices, clean_weather, and features will be written.",
    )
    parser.add_argument(
        "--processed-prefix",
        default="processed",
        help="S3 prefix root for processed datasets.",
    )
    parser.add_argument(
        "--mapping-prefix",
        default="reference/product_mapping",
        help="Optional S3 prefix containing mapping CSV files.",
    )
    parser.add_argument("--lags", default="1,7,14,28", help="Comma-separated lag windows in days.")
    parser.add_argument(
        "--rolling-windows",
        default="3,7,14",
        help="Comma-separated rolling mean windows in days.",
    )
    parser.add_argument(
        "--forward-fill-limit",
        type=int,
        default=7,
        help="Maximum number of consecutive days to forward fill base columns.",
    )
    parser.add_argument(
        "--target-horizon-days",
        type=int,
        default=1,
        help="Forecast horizon in days for target columns.",
    )
    parser.add_argument(
        "--required-feature-columns",
        default="",
        help="Optional comma-separated list of columns that must exist in the final features dataset.",
    )
    parser.add_argument(
        "--inference-prefix",
        default="inference/input",
        help="S3 prefix root where daily inference input payload and manifest will be written.",
    )
    parser.add_argument(
        "--inference-lookback-days",
        type=int,
        default=1,
        help="How many most recent days to include in generated inference input payload (default 1 for daily inference).",
    )
    return parser


def main() -> int:
    args, _ = build_parser().parse_known_args()
    s3_client = boto3.client("s3")

    mapping_tables = load_mapping_tables_from_s3(
        s3_client=s3_client,
        bucket=args.raw_bucket,
        prefix=args.mapping_prefix,
    )
    price_payloads = load_json_payloads_from_s3(
        s3_client=s3_client,
        bucket=args.raw_bucket,
        prefix=args.price_prefix,
    )
    weather_payloads = load_json_payloads_from_s3(
        s3_client=s3_client,
        bucket=args.raw_bucket,
        prefix=args.weather_prefix,
    )
    required_feature_columns = [
        column.strip()
        for column in args.required_feature_columns.split(",")
        if column.strip()
    ]

    bundle = build_dataset_bundle(
        price_payloads=price_payloads,
        weather_payloads=weather_payloads,
        mapping_tables=mapping_tables,
        config=TransformConfig(
            lags=parse_int_list(args.lags),
            rolling_windows=parse_int_list(args.rolling_windows),
            forward_fill_limit=args.forward_fill_limit,
            target_horizon_days=args.target_horizon_days,
        ),
        required_feature_columns=required_feature_columns or None,
    )

    with tempfile.TemporaryDirectory() as temp_dir:
        upload_bundle_to_s3(
            bundle=bundle,
            local_root=Path(temp_dir),
            s3_client=s3_client,
            bucket=args.processed_bucket,
            prefix=args.processed_prefix,
        )
    inference_meta = upload_inference_input_to_s3(
        features=bundle.features,
        s3_client=s3_client,
        bucket=args.processed_bucket,
        inference_prefix=args.inference_prefix,
        lookback_days=args.inference_lookback_days,
    )

    logger.info(
        json.dumps(
            {
                "message": "phase_b_glue_job_completed",
                "processed_bucket": args.processed_bucket,
                "processed_prefix": args.processed_prefix,
                "clean_prices_rows": int(len(bundle.clean_prices)),
                "clean_weather_rows": int(len(bundle.clean_weather)),
                "features_rows": int(len(bundle.features)),
                "validation_status": bundle.validation_report["status"],
                "inference_run_date": inference_meta["run_date"],
                "inference_rows": inference_meta["rows"],
                "inference_payload_key": inference_meta["payload_key"],
                "inference_manifest_key": inference_meta["manifest_key"],
            },
            ensure_ascii=False,
        )
    )
    return 0


def load_json_payloads_from_s3(
    s3_client: Any,
    bucket: str,
    prefix: str,
) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []

    for key in list_s3_keys(s3_client=s3_client, bucket=bucket, prefix=prefix, suffix=".json"):
        response = s3_client.get_object(Bucket=bucket, Key=key)
        payload = json.loads(response["Body"].read().decode("utf-8-sig"))
        payload["_source_key"] = f"s3://{bucket}/{key}"
        payloads.append(payload)

    if not payloads:
        raise ValueError(f"No JSON payloads found in s3://{bucket}/{prefix}")

    return payloads


def load_mapping_tables_from_s3(
    s3_client: Any,
    bucket: str,
    prefix: str,
) -> MappingTables:
    defaults = MappingTables()
    product = {}
    category = {}
    group = {}
    unit = {}

    for key in list_s3_keys(s3_client=s3_client, bucket=bucket, prefix=prefix, suffix=".csv"):
        response = s3_client.get_object(Bucket=bucket, Key=key)
        mapping = load_name_mapping_from_csv_bytes(response["Body"].read())
        lower_key = key.lower()
        if "category" in lower_key:
            category.update(mapping)
        elif "group" in lower_key:
            group.update(mapping)
        elif "unit" in lower_key:
            unit.update(mapping)
        else:
            product.update(mapping)

    return MappingTables(
        product=product,
        category={**defaults.category, **category},
        group={**defaults.group, **group},
        unit={**defaults.unit, **unit},
    )


def list_s3_keys(
    s3_client: Any,
    bucket: str,
    prefix: str,
    suffix: str,
) -> list[str]:
    continuation_token: str | None = None
    keys: list[str] = []

    while True:
        kwargs: dict[str, Any] = {"Bucket": bucket, "Prefix": prefix}
        if continuation_token:
            kwargs["ContinuationToken"] = continuation_token
        response = s3_client.list_objects_v2(**kwargs)
        for item in response.get("Contents", []):
            key = item["Key"]
            if key.endswith(suffix):
                keys.append(key)
        if not response.get("IsTruncated"):
            break
        continuation_token = response.get("NextContinuationToken")

    return sorted(keys)


def upload_bundle_to_s3(
    bundle: DatasetBundle,
    local_root: Path,
    s3_client: Any,
    bucket: str,
    prefix: str,
) -> None:
    write_bundle_to_local(bundle=bundle, output_root=local_root)

    for path in local_root.rglob("*"):
        if path.is_dir():
            continue

        relative_path = path.relative_to(local_root).as_posix()
        s3_key = f"{prefix.rstrip('/')}/{relative_path}"
        s3_client.upload_file(str(path), bucket, s3_key)


def upload_inference_input_to_s3(
    features: pd.DataFrame,
    s3_client: Any,
    bucket: str,
    inference_prefix: str,
    lookback_days: int,
) -> dict[str, Any]:
    run_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    root_prefix = inference_prefix.rstrip("/")
    payload_key = f"{root_prefix}/run_date={run_date}/payload/features.jsonl"
    manifest_key = f"{root_prefix}/run_date={run_date}/meta/input_manifest.parquet"

    frame = features.copy()
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    frame = frame.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)
    if frame.empty:
        raise ValueError("Features dataset is empty; cannot generate inference input.")

    if lookback_days > 0:
        cutoff = frame["date"].max() - pd.Timedelta(days=lookback_days)
        frame = frame[frame["date"] > cutoff].copy().reset_index(drop=True)
        if frame.empty:
            raise ValueError(
                f"No feature rows available in lookback window ({lookback_days} days) for inference input."
            )

    # Drop labels to avoid target leakage in inference payload.
    target_columns = [c for c in frame.columns if c.startswith("target_next_day_")]
    infer_frame = frame.drop(columns=target_columns, errors="ignore").copy()
    infer_frame["date"] = infer_frame["date"].dt.strftime("%Y-%m-%d")

    manifest = pd.DataFrame(
        {
            "row_id": range(len(infer_frame)),
            "date": infer_frame["date"],
            "run_date": run_date,
        }
    )

    records = infer_frame.to_dict(orient="records")
    jsonl_payload = "\n".join(
        json.dumps({"instances": [record]}, ensure_ascii=False, default=str) for record in records
    ) + "\n"

    s3_client.put_object(
        Bucket=bucket,
        Key=payload_key,
        Body=jsonl_payload.encode("utf-8"),
        ContentType="application/json",
    )

    manifest_buffer = io.BytesIO()
    manifest.to_parquet(manifest_buffer, index=False)
    s3_client.put_object(
        Bucket=bucket,
        Key=manifest_key,
        Body=manifest_buffer.getvalue(),
        ContentType="application/octet-stream",
    )

    return {
        "run_date": run_date,
        "rows": int(len(infer_frame)),
        "payload_key": payload_key,
        "manifest_key": manifest_key,
    }


if __name__ == "__main__":
    main()
