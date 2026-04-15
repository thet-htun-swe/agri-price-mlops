import os
import json
import boto3
import pandas as pd
from io import BytesIO
from datetime import datetime, timezone

REGION = os.environ.get("AWS_REGION", "us-east-1")
s3 = boto3.client("s3", region_name=REGION)

BUCKET = os.environ["BUCKET"]
RAW_BASE = os.environ.get("RAW_BASE", "predictions/raw/")
CURATED_BASE = os.environ.get("CURATED_BASE", "predictions/curated/")
LATEST_BASE = os.environ.get("LATEST_BASE", "predictions/curated/latest/")
META_BASE = os.environ.get("META_BASE", "inference/input/")
MODEL_PACKAGE_GROUP = os.environ.get("MODEL_PACKAGE_GROUP", "agri-price-multi-output")

def _list_keys(prefix):
    resp = s3.list_objects_v2(Bucket=BUCKET, Prefix=prefix)
    return [x["Key"] for x in resp.get("Contents", [])]

def lambda_handler(event, context):
    run_date = event.get("run_date") if isinstance(event, dict) else None
    if not run_date:
        run_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    raw_prefix = f"{RAW_BASE}run_date={run_date}/"
    meta_prefix = f"{META_BASE}run_date={run_date}/meta/"
    curated_prefix = f"{CURATED_BASE}run_date={run_date}/"

    raw_keys = [k for k in _list_keys(raw_prefix) if k.endswith(".out")]
    if not raw_keys:
        raise RuntimeError(f"No .out files found in s3://{BUCKET}/{raw_prefix}")

    manifest_key = f"{meta_prefix}input_manifest.parquet"
    manifest_obj = s3.get_object(Bucket=BUCKET, Key=manifest_key)
    manifest = pd.read_parquet(BytesIO(manifest_obj["Body"].read()))

    pred_rows = []
    for k in raw_keys:
        text = s3.get_object(Bucket=BUCKET, Key=k)["Body"].read().decode("utf-8")
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            payload = json.loads(line)
            pred_rows.extend(payload.get("predictions", []))

    pred_df = pd.DataFrame(pred_rows).reset_index(drop=True)
    if len(pred_df) != len(manifest):
        raise RuntimeError(f"Prediction rows {len(pred_df)} != manifest rows {len(manifest)}")

    curated = pd.DataFrame({
        "date": manifest["date"],
        "target_next_day_price_coriander_pred": pred_df["target_next_day_price_coriander"],
        "target_next_day_price_kale_pred": pred_df["target_next_day_price_kale"],
        "target_next_day_price_lime_pred": pred_df["target_next_day_price_lime"],
        "target_next_day_price_orange_pred": pred_df["target_next_day_price_orange"],
        "target_next_day_price_red_chili_pred": pred_df["target_next_day_price_red_chili"],
        "model_package_group": MODEL_PACKAGE_GROUP,
        "run_date": run_date,
    })

    buf = BytesIO()
    curated.to_parquet(buf, index=False)
    parquet_bytes = buf.getvalue()

    out_key = f"{curated_prefix}predictions.parquet"
    s3.put_object(Bucket=BUCKET, Key=out_key, Body=parquet_bytes)

    latest_key = f"{LATEST_BASE.rstrip('/')}/predictions.parquet"
    s3.put_object(Bucket=BUCKET, Key=latest_key, Body=parquet_bytes)

    latest_json_key = f"{LATEST_BASE.rstrip('/')}/predictions.json"
    latest_json_payload = json.dumps(
        {
            "run_date": run_date,
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "row_count": int(len(curated)),
            "data": curated.to_dict(orient="records"),
        },
        ensure_ascii=False,
        default=str,
    ).encode("utf-8")
    s3.put_object(
        Bucket=BUCKET,
        Key=latest_json_key,
        Body=latest_json_payload,
        ContentType="application/json",
    )

    return {
        "status": "ok",
        "run_date": run_date,
        "output": f"s3://{BUCKET}/{out_key}",
        "latest_output": f"s3://{BUCKET}/{latest_key}",
        "latest_json_output": f"s3://{BUCKET}/{latest_json_key}",
    }
