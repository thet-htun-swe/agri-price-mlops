from __future__ import annotations

import csv
import io
import json
import logging
import re
import shutil
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import pandas as pd


logger = logging.getLogger(__name__)

WEATHER_COLUMNS = (
    "temperature_2m_mean",
    "precipitation_sum",
    "relative_humidity_2m_mean",
)
CALENDAR_COLUMNS = (
    "year",
    "month",
    "day_of_month",
    "day_of_week",
    "week_of_year",
    "day_of_year",
    "quarter",
    "is_weekend",
)
PRICE_OUTPUT_COLUMNS = (
    "date",
    "product_id",
    "product_name_th",
    "product_name_en",
    "product_name_en_key",
    "category_name_th",
    "category_name_en",
    "group_name_th",
    "group_name_en",
    "unit_th",
    "unit_en",
    "price_min",
    "price_max",
    "price_mid",
    "price_spread",
    "source_record_count",
    "latest_source_key",
    "fetched_at_utc",
    "year",
    "month",
)
WEATHER_OUTPUT_COLUMNS = (
    "date",
    "temperature_2m_mean",
    "precipitation_sum",
    "relative_humidity_2m_mean",
    "latitude",
    "longitude",
    "timezone",
    "source_record_count",
    "latest_source_key",
    "fetched_at_utc",
    "year",
    "month",
)
MACHINE_FRIENDLY_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
MOJIBAKE_MARKERS = ("\u00c3", "\u00c2", "\u00e0\u00b8", "\u00e0\u00b9", "\u00e2")
MANAGED_METADATA_FILES = ("_SUCCESS",)


class PhaseBValidationError(ValueError):
    """Raised when the Phase B transformation fails validation."""


@dataclass(frozen=True)
class TransformConfig:
    lags: tuple[int, ...] = (1, 7, 14, 28)
    rolling_windows: tuple[int, ...] = (3, 7, 14)
    forward_fill_limit: int = 7
    target_horizon_days: int = 1


@dataclass(frozen=True)
class MappingTables:
    product: dict[str, str] = field(default_factory=dict)
    category: dict[str, str] = field(
        default_factory=lambda: {
            "\u0e02\u0e32\u0e22\u0e1b\u0e25\u0e35\u0e01": "retail",
        }
    )
    group: dict[str, str] = field(
        default_factory=lambda: {
            "\u0e1c\u0e31\u0e01\u0e2a\u0e14": "fresh_vegetables",
            "\u0e40\u0e19\u0e37\u0e49\u0e2d\u0e2a\u0e31\u0e15\u0e27\u0e4c": "meat",
        }
    )
    unit: dict[str, str] = field(
        default_factory=lambda: {
            "\u0e1a\u0e32\u0e17/\u0e01\u0e01.": "baht_per_kg",
        }
    )


@dataclass(frozen=True)
class DatasetBundle:
    clean_prices: pd.DataFrame
    clean_weather: pd.DataFrame
    features: pd.DataFrame
    validation_report: dict[str, Any]
    feature_schema: dict[str, Any]


def run_local_phase_b(
    price_dir: str | Path,
    weather_dir: str | Path,
    mapping_dir: str | Path | None,
    output_root: str | Path,
    config: TransformConfig | None = None,
    required_feature_columns: Sequence[str] | None = None,
) -> DatasetBundle:
    config = config or TransformConfig()
    mapping_tables = load_mapping_tables_from_directory(mapping_dir)
    price_payloads = load_json_payloads_from_directory(price_dir)
    weather_payloads = load_json_payloads_from_directory(weather_dir)

    bundle = build_dataset_bundle(
        price_payloads=price_payloads,
        weather_payloads=weather_payloads,
        mapping_tables=mapping_tables,
        config=config,
        required_feature_columns=required_feature_columns,
    )
    write_bundle_to_local(bundle=bundle, output_root=output_root)
    return bundle


def build_dataset_bundle(
    price_payloads: Sequence[dict[str, Any]],
    weather_payloads: Sequence[dict[str, Any]],
    mapping_tables: MappingTables | None = None,
    config: TransformConfig | None = None,
    required_feature_columns: Sequence[str] | None = None,
) -> DatasetBundle:
    config = config or TransformConfig()
    mapping_tables = mapping_tables or MappingTables()

    clean_prices_internal = normalize_price_payloads(
        payloads=price_payloads,
        mapping_tables=mapping_tables,
    )
    clean_weather_internal = normalize_weather_payloads(payloads=weather_payloads)
    features_internal, expected_price_columns = build_features_dataset(
        clean_prices=clean_prices_internal,
        clean_weather=clean_weather_internal,
        mapping_tables=mapping_tables,
        config=config,
    )

    feature_schema = build_feature_schema(
        features=features_internal,
        expected_price_columns=expected_price_columns,
        config=config,
    )
    validation_report = build_validation_report(
        clean_prices=clean_prices_internal,
        clean_weather=clean_weather_internal,
        features=features_internal,
        feature_schema=feature_schema,
        config=config,
        required_feature_columns=required_feature_columns,
    )

    clean_prices = finalize_clean_prices(clean_prices_internal)
    clean_weather = finalize_clean_weather(clean_weather_internal)
    features = finalize_features(features_internal)

    return DatasetBundle(
        clean_prices=clean_prices,
        clean_weather=clean_weather,
        features=features,
        validation_report=validation_report,
        feature_schema=feature_schema,
    )


def load_json_payloads_from_directory(root_dir: str | Path) -> list[dict[str, Any]]:
    root_path = Path(root_dir)
    if not root_path.exists():
        raise PhaseBValidationError(f"Input directory does not exist: {root_path}")

    payloads: list[dict[str, Any]] = []
    for path in sorted(root_path.rglob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
        payload["_source_key"] = str(path.as_posix())
        payloads.append(payload)

    if not payloads:
        raise PhaseBValidationError(f"No JSON payloads found under: {root_path}")

    return payloads


def load_mapping_tables_from_directory(mapping_dir: str | Path | None) -> MappingTables:
    if mapping_dir is None:
        return MappingTables()

    mapping_path = Path(mapping_dir)
    if not mapping_path.exists():
        logger.warning("Mapping directory not found; using built-in defaults: %s", mapping_path)
        return MappingTables()

    mapping_files = sorted(mapping_path.glob("*.csv"))
    if not mapping_files:
        logger.warning("No mapping CSV files found; using built-in defaults: %s", mapping_path)
        return MappingTables()

    product = {}
    category = {}
    group = {}
    unit = {}

    for csv_path in mapping_files:
        mapping = load_name_mapping_from_csv_bytes(csv_path.read_bytes())
        name = csv_path.name.lower()
        if "category" in name:
            category.update(mapping)
        elif "group" in name:
            group.update(mapping)
        elif "unit" in name:
            unit.update(mapping)
        else:
            product.update(mapping)

    defaults = MappingTables()
    return MappingTables(
        product=product,
        category={**defaults.category, **category},
        group={**defaults.group, **group},
        unit={**defaults.unit, **unit},
    )


def load_name_mapping_from_csv_bytes(raw_bytes: bytes) -> dict[str, str]:
    text = raw_bytes.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    mapping: dict[str, str] = {}

    for row in reader:
        thai_name = normalize_text(row.get("thai_name"))
        english_name = normalize_text(row.get("english_name"))
        if thai_name and english_name:
            mapping[thai_name] = english_name

    return mapping


def normalize_price_payloads(
    payloads: Sequence[dict[str, Any]],
    mapping_tables: MappingTables,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []

    for payload in payloads:
        if payload.get("source") != "price":
            continue

        raw_response = payload.get("raw_response") or {}
        product_id = normalize_text(raw_response.get("product_id")) or normalize_text(
            ((payload.get("request") or {}).get("params") or {}).get("product_id")
        )
        product_name_th = normalize_text(raw_response.get("product_name"))
        product_name_en = normalize_text(raw_response.get("product_desc_en")) or mapping_tables.product.get(
            product_name_th or "",
            product_id or "unknown_product",
        )
        category_name_th = normalize_text(raw_response.get("category_name"))
        group_name_th = normalize_text(raw_response.get("group_name"))
        unit_th = normalize_text(raw_response.get("unit"))

        for entry in raw_response.get("price_list") or []:
            rows.append(
                {
                    "date": entry.get("date"),
                    "product_id": product_id,
                    "product_name_th": product_name_th,
                    "product_name_en": product_name_en,
                    "product_name_en_key": make_machine_name(product_name_en or product_id or "unknown_product"),
                    "category_name_th": category_name_th,
                    "category_name_en": translate_text(category_name_th, mapping_tables.category),
                    "group_name_th": group_name_th,
                    "group_name_en": translate_text(group_name_th, mapping_tables.group),
                    "unit_th": unit_th,
                    "unit_en": translate_text(unit_th, mapping_tables.unit),
                    "price_min": entry.get("price_min"),
                    "price_max": entry.get("price_max"),
                    "latest_source_key": payload.get("_source_key"),
                    "fetched_at_utc": payload.get("fetched_at_utc"),
                }
            )

    if not rows:
        raise PhaseBValidationError("No price observations found in the raw payloads.")

    clean_prices = pd.DataFrame(rows)
    clean_prices["date"] = pd.to_datetime(clean_prices["date"], errors="coerce").dt.normalize()
    clean_prices["fetched_at_utc"] = pd.to_datetime(
        clean_prices["fetched_at_utc"],
        utc=True,
        errors="coerce",
    )
    clean_prices["price_min"] = pd.to_numeric(clean_prices["price_min"], errors="coerce")
    clean_prices["price_max"] = pd.to_numeric(clean_prices["price_max"], errors="coerce")
    clean_prices["price_mid"] = clean_prices[["price_min", "price_max"]].mean(axis=1)
    clean_prices["price_spread"] = clean_prices["price_max"] - clean_prices["price_min"]

    clean_prices = clean_prices.dropna(subset=["date", "product_id"]).sort_values(
        ["date", "product_id", "fetched_at_utc", "latest_source_key"],
        kind="stable",
    )
    clean_prices["source_record_count"] = clean_prices.groupby(["date", "product_id"])["product_id"].transform("size")
    clean_prices = clean_prices.drop_duplicates(subset=["date", "product_id"], keep="last").reset_index(drop=True)
    clean_prices["year"] = clean_prices["date"].dt.year.astype("int32")
    clean_prices["month"] = clean_prices["date"].dt.month.astype("int32")

    return clean_prices[list(PRICE_OUTPUT_COLUMNS)]


def normalize_weather_payloads(payloads: Sequence[dict[str, Any]]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []

    for payload in payloads:
        if payload.get("source") != "weather":
            continue

        raw_response = payload.get("raw_response") or {}
        daily = raw_response.get("daily") or {}
        dates = daily.get("time") or []

        for index, date_value in enumerate(dates):
            rows.append(
                {
                    "date": date_value,
                    "temperature_2m_mean": get_daily_value(daily, "temperature_2m_mean", index),
                    "precipitation_sum": get_daily_value(daily, "precipitation_sum", index),
                    "relative_humidity_2m_mean": get_daily_value(daily, "relative_humidity_2m_mean", index),
                    "latitude": raw_response.get("latitude"),
                    "longitude": raw_response.get("longitude"),
                    "timezone": normalize_text(raw_response.get("timezone")),
                    "latest_source_key": payload.get("_source_key"),
                    "fetched_at_utc": payload.get("fetched_at_utc"),
                }
            )

    if not rows:
        raise PhaseBValidationError("No weather observations found in the raw payloads.")

    clean_weather = pd.DataFrame(rows)
    clean_weather["date"] = pd.to_datetime(clean_weather["date"], errors="coerce").dt.normalize()
    clean_weather["fetched_at_utc"] = pd.to_datetime(
        clean_weather["fetched_at_utc"],
        utc=True,
        errors="coerce",
    )
    for column in WEATHER_COLUMNS + ("latitude", "longitude"):
        clean_weather[column] = pd.to_numeric(clean_weather[column], errors="coerce")

    clean_weather = clean_weather.dropna(subset=["date"]).sort_values(
        ["date", "fetched_at_utc", "latest_source_key"],
        kind="stable",
    )
    clean_weather["source_record_count"] = clean_weather.groupby(["date"])["date"].transform("size")
    clean_weather = clean_weather.drop_duplicates(subset=["date"], keep="last").reset_index(drop=True)
    clean_weather["year"] = clean_weather["date"].dt.year.astype("int32")
    clean_weather["month"] = clean_weather["date"].dt.month.astype("int32")

    return clean_weather[list(WEATHER_OUTPUT_COLUMNS)]


def build_features_dataset(
    clean_prices: pd.DataFrame,
    clean_weather: pd.DataFrame,
    mapping_tables: MappingTables,
    config: TransformConfig,
) -> tuple[pd.DataFrame, list[str]]:
    if clean_prices.empty:
        raise PhaseBValidationError("The clean_prices dataset is empty after normalization.")

    if clean_weather.empty:
        raise PhaseBValidationError("The clean_weather dataset is empty after normalization.")

    observed_price_columns = sorted(
        {f"price_{value}" for value in clean_prices["product_name_en_key"].dropna().astype(str).unique()}
    )
    mapped_price_columns = sorted(
        {f"price_{make_machine_name(value)}" for value in mapping_tables.product.values() if normalize_text(value)}
    )
    expected_price_columns = sorted(set(observed_price_columns) | set(mapped_price_columns))
    if not expected_price_columns:
        raise PhaseBValidationError("Unable to determine expected price columns for the features dataset.")

    pivoted_prices = (
        clean_prices.pivot_table(
            index="date",
            columns="product_name_en_key",
            values="price_mid",
            aggfunc="last",
        )
        .rename(columns=lambda value: f"price_{value}")
        .sort_index(axis=1)
    )

    for column in expected_price_columns:
        if column not in pivoted_prices.columns:
            pivoted_prices[column] = float("nan")

    pivoted_prices = pivoted_prices[expected_price_columns].reset_index()
    base_weather = clean_weather[["date", *WEATHER_COLUMNS]].copy()
    features = pd.merge(base_weather, pivoted_prices, on="date", how="outer").sort_values("date").reset_index(drop=True)

    date_range = pd.date_range(features["date"].min(), features["date"].max(), freq="D")
    features = features.set_index("date").reindex(date_range).rename_axis("date").reset_index()

    base_columns = list(WEATHER_COLUMNS) + expected_price_columns
    raw_target_frame = features[expected_price_columns].copy()

    for column in base_columns:
        if column not in features.columns:
            features[column] = float("nan")
        features[column] = pd.to_numeric(features[column], errors="coerce")
        features[f"{column}_was_missing"] = features[column].isna().astype("int8")
        features[column] = features[column].ffill(limit=config.forward_fill_limit)

    for lag in config.lags:
        for column in base_columns:
            features[f"{column}_lag_{lag}"] = features[column].shift(lag)

    for window in config.rolling_windows:
        for column in base_columns:
            features[f"{column}_rolling_mean_{window}"] = features[column].rolling(
                window=window,
                min_periods=1,
            ).mean()

    features["year"] = features["date"].dt.year.astype("int32")
    features["month"] = features["date"].dt.month.astype("int32")
    features["day_of_month"] = features["date"].dt.day.astype("int32")
    features["day_of_week"] = features["date"].dt.dayofweek.astype("int32")
    features["week_of_year"] = features["date"].dt.isocalendar().week.astype("int32")
    features["day_of_year"] = features["date"].dt.dayofyear.astype("int32")
    features["quarter"] = features["date"].dt.quarter.astype("int32")
    features["is_weekend"] = features["day_of_week"].isin([5, 6]).astype("int8")

    for column in expected_price_columns:
        features[f"target_next_day_{column}"] = raw_target_frame[column].shift(-config.target_horizon_days)

    ordered_columns = build_feature_column_order(features.columns, expected_price_columns)
    return features[ordered_columns], expected_price_columns


def build_feature_column_order(
    all_columns: Iterable[str],
    expected_price_columns: Sequence[str],
) -> list[str]:
    all_columns = list(all_columns)
    missing_indicator_columns = sorted(column for column in all_columns if column.endswith("_was_missing"))
    lag_columns = sorted(column for column in all_columns if "_lag_" in column)
    rolling_columns = sorted(column for column in all_columns if "_rolling_mean_" in column)
    target_columns = sorted(column for column in all_columns if column.startswith("target_next_day_"))

    ordered_columns = [
        "date",
        *WEATHER_COLUMNS,
        *sorted(expected_price_columns),
        *missing_indicator_columns,
        *lag_columns,
        *rolling_columns,
        *CALENDAR_COLUMNS,
        *target_columns,
    ]

    return [column for column in ordered_columns if column in all_columns]


def build_feature_schema(
    features: pd.DataFrame,
    expected_price_columns: Sequence[str],
    config: TransformConfig,
) -> dict[str, Any]:
    target_columns = sorted(column for column in features.columns if column.startswith("target_next_day_"))
    lag_columns = sorted(column for column in features.columns if "_lag_" in column)
    rolling_columns = sorted(column for column in features.columns if "_rolling_mean_" in column)
    missing_indicator_columns = sorted(column for column in features.columns if column.endswith("_was_missing"))

    return {
        "base_weather_columns": list(WEATHER_COLUMNS),
        "base_price_columns": list(expected_price_columns),
        "missing_indicator_columns": missing_indicator_columns,
        "lag_columns": lag_columns,
        "rolling_columns": rolling_columns,
        "calendar_columns": list(CALENDAR_COLUMNS),
        "target_columns": target_columns,
        "all_columns": list(features.columns),
        "forward_fill_limit": config.forward_fill_limit,
        "lags": list(config.lags),
        "rolling_windows": list(config.rolling_windows),
        "target_horizon_days": config.target_horizon_days,
    }


def build_validation_report(
    clean_prices: pd.DataFrame,
    clean_weather: pd.DataFrame,
    features: pd.DataFrame,
    feature_schema: Mapping[str, Any],
    config: TransformConfig,
    required_feature_columns: Sequence[str] | None = None,
) -> dict[str, Any]:
    default_required_columns = [
        *WEATHER_COLUMNS,
        *feature_schema["base_price_columns"],
        "year",
        "month",
        "day_of_week",
        "is_weekend",
        *feature_schema["target_columns"],
    ]
    required_feature_columns = list(required_feature_columns or default_required_columns)

    duplicate_feature_dates = int(features["date"].duplicated().sum())
    invalid_feature_columns = [
        column for column in features.columns if not MACHINE_FRIENDLY_PATTERN.fullmatch(column)
    ]
    missing_required_feature_columns = [
        column for column in required_feature_columns if column not in features.columns
    ]
    critical_null_counts = {
        column: int(features[column].isna().sum())
        for column in ("date", "year", "month")
        if column in features.columns
    }
    critical_null_counts = {
        column: count for column, count in critical_null_counts.items() if count
    }
    columns_with_missing_values = {
        column: int(count)
        for column, count in features.isna().sum().items()
        if count > 0
    }

    report = {
        "status": "passed",
        "clean_prices": {
            "row_count": int(len(clean_prices)),
            "duplicate_date_product_rows": int(clean_prices.duplicated(subset=["date", "product_id"]).sum()),
        },
        "clean_weather": {
            "row_count": int(len(clean_weather)),
            "duplicate_date_rows": int(clean_weather.duplicated(subset=["date"]).sum()),
        },
        "features": {
            "row_count": int(len(features)),
            "duplicate_dates": duplicate_feature_dates,
            "invalid_column_names": invalid_feature_columns,
            "missing_required_feature_columns": missing_required_feature_columns,
            "critical_null_counts": critical_null_counts,
            "partition_columns": {
                "columns": ["year", "month"],
                "present": all(column in features.columns for column in ("year", "month")),
                "explanation": "Datasets are written as Parquet partitioned by year and month directories.",
            },
            "columns_with_missing_values": columns_with_missing_values,
            "missing_value_policy": {
                "forward_fill_limit_days": config.forward_fill_limit,
                "policy": "Forward fill weather and price base columns only. No backward fill is applied.",
                "expected_missing_explanations": [
                    "Leading gaps remain null because backward fill is disabled.",
                    "Gaps longer than the forward-fill limit remain null.",
                    "Lag features are null until enough history exists.",
                    "Target columns are null for dates without a future observation at the configured horizon.",
                ],
            },
        },
        "required_feature_columns": required_feature_columns,
        "feature_schema": {
            "base_price_columns": feature_schema["base_price_columns"],
            "base_weather_columns": feature_schema["base_weather_columns"],
            "target_columns": feature_schema["target_columns"],
        },
    }

    if (
        duplicate_feature_dates
        or invalid_feature_columns
        or missing_required_feature_columns
        or critical_null_counts
        or report["clean_prices"]["duplicate_date_product_rows"]
        or report["clean_weather"]["duplicate_date_rows"]
        or len(features) == 0
    ):
        report["status"] = "failed"
        raise PhaseBValidationError(
            "Phase B validation failed: "
            + json.dumps(
                {
                    "duplicate_dates": duplicate_feature_dates,
                    "invalid_column_names": invalid_feature_columns,
                    "missing_required_feature_columns": missing_required_feature_columns,
                    "critical_null_counts": critical_null_counts,
                },
                ensure_ascii=False,
            )
        )

    return report


def finalize_clean_prices(clean_prices: pd.DataFrame) -> pd.DataFrame:
    output = clean_prices.copy()
    output["date"] = output["date"].dt.strftime("%Y-%m-%d")
    output["fetched_at_utc"] = output["fetched_at_utc"].dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    return output[list(PRICE_OUTPUT_COLUMNS)]


def finalize_clean_weather(clean_weather: pd.DataFrame) -> pd.DataFrame:
    output = clean_weather.copy()
    output["date"] = output["date"].dt.strftime("%Y-%m-%d")
    output["fetched_at_utc"] = output["fetched_at_utc"].dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    return output[list(WEATHER_OUTPUT_COLUMNS)]


def finalize_features(features: pd.DataFrame) -> pd.DataFrame:
    output = features.copy()
    output["date"] = output["date"].dt.strftime("%Y-%m-%d")
    return output


def write_bundle_to_local(bundle: DatasetBundle, output_root: str | Path) -> None:
    root_path = Path(output_root)
    root_path.mkdir(parents=True, exist_ok=True)

    clean_prices_root = root_path / "clean_prices"
    clean_weather_root = root_path / "clean_weather"
    features_root = root_path / "features"

    write_partitioned_parquet(bundle.clean_prices, clean_prices_root)
    write_partitioned_parquet(bundle.clean_weather, clean_weather_root)
    write_partitioned_parquet(bundle.features, features_root)

    metadata_root = features_root / "_meta"
    metadata_root.mkdir(parents=True, exist_ok=True)
    (metadata_root / "validation_report.json").write_text(
        json.dumps(bundle.validation_report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (metadata_root / "feature_schema.json").write_text(
        json.dumps(bundle.feature_schema, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (features_root / "_SUCCESS").write_text("", encoding="utf-8")


def write_partitioned_parquet(dataframe: pd.DataFrame, dataset_root: str | Path) -> None:
    dataset_path = Path(dataset_root)
    dataset_path.mkdir(parents=True, exist_ok=True)
    clear_managed_dataset_outputs(dataset_path)
    dataframe.to_parquet(
        dataset_path,
        engine="pyarrow",
        index=False,
        partition_cols=["year", "month"],
    )


def clear_managed_dataset_outputs(dataset_root: Path) -> None:
    for child in dataset_root.iterdir():
        if child.is_dir() and child.name.startswith("year="):
            shutil.rmtree(child)
        elif child.is_dir() and child.name == "_meta":
            shutil.rmtree(child)
        elif child.is_file() and child.name in MANAGED_METADATA_FILES:
            child.unlink()


def normalize_text(value: Any) -> str | None:
    if value is None:
        return None

    if not isinstance(value, str):
        value = str(value)

    value = repair_mojibake(value).strip()
    if not value:
        return None

    return " ".join(unicodedata.normalize("NFKC", value).split())


def repair_mojibake(value: str) -> str:
    if not any(marker in value for marker in MOJIBAKE_MARKERS):
        return value

    try:
        repaired = value.encode("cp1252").decode("utf-8")
    except (UnicodeError, LookupError):
        return value

    return repaired


def translate_text(value: str | None, mapping: Mapping[str, str]) -> str | None:
    if value is None:
        return None
    return normalize_text(mapping.get(value)) or None


def make_machine_name(value: str) -> str:
    normalized = normalize_text(value) or "unnamed"
    normalized = normalized.encode("ascii", "ignore").decode("ascii")
    normalized = normalized.lower()
    normalized = re.sub(r"[^a-z0-9]+", "_", normalized).strip("_")
    return normalized or "unnamed"


def get_daily_value(daily: Mapping[str, Sequence[Any]], column: str, index: int) -> Any:
    values = daily.get(column) or []
    if index >= len(values):
        return None
    return values[index]
