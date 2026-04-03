from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd

from glue.jobs.phase_b_transform import TransformConfig, run_local_phase_b


THAI_CORIANDER = "\u0e1c\u0e31\u0e01\u0e0a\u0e35 \u0e04\u0e31\u0e14 (\u0e1a\u0e32\u0e17/\u0e01\u0e01.)"
THAI_KALE = "\u0e1c\u0e31\u0e01\u0e04\u0e30\u0e19\u0e49\u0e32 \u0e04\u0e31\u0e14"
THAI_LIME = "\u0e21\u0e30\u0e19\u0e32\u0e27 \u0e40\u0e1a\u0e2d\u0e23\u0e4c 1-2"
CATEGORY_RETAIL = "\u0e02\u0e32\u0e22\u0e1b\u0e25\u0e35\u0e01"
GROUP_FRESH = "\u0e1c\u0e31\u0e01\u0e2a\u0e14"
UNIT_BAHT_PER_KG = "\u0e1a\u0e32\u0e17/\u0e01\u0e01."


def test_phase_b_builds_partitioned_outputs_and_stable_features(tmp_path: Path) -> None:
    price_dir = tmp_path / "raw" / "price"
    weather_dir = tmp_path / "raw" / "weather"
    mapping_dir = tmp_path / "mapping"
    output_root = tmp_path / "processed"

    price_dir.mkdir(parents=True)
    weather_dir.mkdir(parents=True)
    mapping_dir.mkdir(parents=True)

    write_mapping_csv(
        mapping_dir / "mapping_name.csv",
        [
            (THAI_CORIANDER, "Coriander"),
            (THAI_KALE, "Kale"),
            (THAI_LIME, "Lime"),
        ],
    )
    write_mapping_csv(mapping_dir / "category_mapping.csv", [(CATEGORY_RETAIL, "retail")])
    write_mapping_csv(mapping_dir / "group_mapping.csv", [(GROUP_FRESH, "fresh_vegetables")])
    write_mapping_csv(mapping_dir / "unit_mapping.csv", [(UNIT_BAHT_PER_KG, "baht_per_kg")])

    write_json(
        price_dir / "price-coriander-1.json",
        price_payload(
            product_id="P13001",
            product_name=THAI_CORIANDER,
            date_value="2026-04-01T00:00:00",
            price_min=10.0,
            price_max=12.0,
            fetched_at="2026-04-02T00:00:00+00:00",
        ),
    )
    write_json(
        price_dir / "price-coriander-2.json",
        price_payload(
            product_id="P13001",
            product_name=THAI_CORIANDER,
            date_value="2026-04-01T00:00:00",
            price_min=12.0,
            price_max=14.0,
            fetched_at="2026-04-02T01:00:00+00:00",
        ),
    )
    write_json(
        price_dir / "price-kale-1.json",
        price_payload(
            product_id="P13002",
            product_name=THAI_KALE,
            date_value="2026-04-01T00:00:00",
            price_min=20.0,
            price_max=24.0,
            fetched_at="2026-04-02T00:30:00+00:00",
        ),
    )
    write_json(
        price_dir / "price-coriander-3.json",
        price_payload(
            product_id="P13001",
            product_name=THAI_CORIANDER,
            date_value="2026-04-03T00:00:00",
            price_min=14.0,
            price_max=16.0,
            fetched_at="2026-04-03T01:00:00+00:00",
        ),
    )
    write_json(
        weather_dir / "weather-1.json",
        weather_payload(
            dates=["2026-04-01", "2026-04-02", "2026-04-03"],
            temperatures=[30.0, 31.0, 32.0],
            precipitation=[0.0, 1.0, 0.0],
            humidity=[80.0, None, 82.0],
            fetched_at="2026-04-03T02:00:00+00:00",
        ),
    )

    bundle = run_local_phase_b(
        price_dir=price_dir,
        weather_dir=weather_dir,
        mapping_dir=mapping_dir,
        output_root=output_root,
        config=TransformConfig(
            lags=(1, 2),
            rolling_windows=(2,),
            forward_fill_limit=7,
            target_horizon_days=1,
        ),
    )

    assert bundle.validation_report["status"] == "passed"
    assert bundle.validation_report["features"]["duplicate_dates"] == 0
    assert bundle.clean_prices["source_record_count"].max() == 2

    clean_prices = bundle.clean_prices.set_index(["date", "product_id"])
    assert clean_prices.loc[("2026-04-01", "P13001"), "category_name_en"] == "retail"
    assert clean_prices.loc[("2026-04-01", "P13001"), "group_name_en"] == "fresh_vegetables"
    assert clean_prices.loc[("2026-04-01", "P13001"), "unit_en"] == "baht_per_kg"
    assert clean_prices.loc[("2026-04-01", "P13001"), "price_mid"] == 13.0

    features = bundle.features.set_index("date")
    assert "price_coriander" in features.columns
    assert "price_kale" in features.columns
    assert "price_lime" in features.columns
    assert "target_next_day_price_coriander" in features.columns
    assert "temperature_2m_mean_lag_1" in features.columns
    assert all(re.fullmatch(r"[a-z][a-z0-9_]*", column) for column in bundle.features.columns)

    assert features.loc["2026-04-02", "price_coriander"] == 13.0
    assert features.loc["2026-04-02", "price_coriander_was_missing"] == 1
    assert pd.isna(features.loc["2026-04-01", "target_next_day_price_coriander"])
    assert features.loc["2026-04-02", "target_next_day_price_coriander"] == 15.0
    assert features.loc["2026-04-02", "relative_humidity_2m_mean"] == 80.0
    assert features.loc["2026-04-02", "relative_humidity_2m_mean_was_missing"] == 1
    assert pd.isna(features.loc["2026-04-02", "price_lime"])
    assert pd.isna(features.loc["2026-04-02", "target_next_day_price_lime"])

    parquet_features = pd.read_parquet(output_root / "features")
    parquet_clean_prices = pd.read_parquet(output_root / "clean_prices")
    parquet_clean_weather = pd.read_parquet(output_root / "clean_weather")

    assert len(parquet_features) == 3
    assert len(parquet_clean_prices) == 3
    assert len(parquet_clean_weather) == 3
    assert (output_root / "features" / "_meta" / "validation_report.json").exists()
    assert (output_root / "features" / "_meta" / "feature_schema.json").exists()
    assert any(path.name.startswith("year=") for path in (output_root / "features").iterdir())

    report = json.loads((output_root / "features" / "_meta" / "validation_report.json").read_text(encoding="utf-8"))
    assert report["status"] == "passed"
    assert report["features"]["missing_required_feature_columns"] == []
    assert report["required_feature_columns"].count("price_lime") == 1


def price_payload(
    product_id: str,
    product_name: str,
    date_value: str,
    price_min: float,
    price_max: float,
    fetched_at: str,
) -> dict:
    return {
        "project": "agri-price",
        "environment": "dev",
        "source": "price",
        "fetched_at_utc": fetched_at,
        "request": {
            "url": "https://example.invalid/prices",
            "params": {
                "product_id": product_id,
                "from_date": date_value[:10],
                "to_date": date_value[:10],
            },
        },
        "http_status_code": 200,
        "raw_response": {
            "product_id": product_id,
            "product_name": product_name,
            "product_desc_en": "",
            "product_desc_th": "",
            "category_name": CATEGORY_RETAIL,
            "group_name": GROUP_FRESH,
            "unit": UNIT_BAHT_PER_KG,
            "price_min_avg": price_min,
            "price_max_avg": price_max,
            "price_list": [
                {
                    "date": date_value,
                    "price_min": price_min,
                    "price_max": price_max,
                }
            ],
        },
    }


def weather_payload(
    dates: list[str],
    temperatures: list[float | None],
    precipitation: list[float | None],
    humidity: list[float | None],
    fetched_at: str,
) -> dict:
    return {
        "project": "agri-price",
        "environment": "dev",
        "source": "weather",
        "fetched_at_utc": fetched_at,
        "request_url": "https://example.invalid/weather",
        "query_params": {
            "latitude": "13.7563",
            "longitude": "100.5018",
            "start_date": dates[0],
            "end_date": dates[-1],
            "daily": "temperature_2m_mean,precipitation_sum,relative_humidity_2m_mean",
            "timezone": "Asia/Bangkok",
        },
        "http_status_code": 200,
        "raw_response": {
            "latitude": 13.7563,
            "longitude": 100.5018,
            "timezone": "Asia/Bangkok",
            "daily": {
                "time": dates,
                "temperature_2m_mean": temperatures,
                "precipitation_sum": precipitation,
                "relative_humidity_2m_mean": humidity,
            },
        },
    }


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_mapping_csv(path: Path, rows: list[tuple[str, str]]) -> None:
    lines = ["thai_name,english_name"]
    lines.extend(f"{thai},{english}" for thai, english in rows)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
