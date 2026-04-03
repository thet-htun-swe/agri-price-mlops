from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from glue.jobs.phase_b_transform import TransformConfig, run_local_phase_b


def parse_int_list(raw_value: str) -> tuple[int, ...]:
    return tuple(int(part.strip()) for part in raw_value.split(",") if part.strip())


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build Phase B processed datasets from local raw files.")
    parser.add_argument("--price-dir", default="data/raw/price", help="Directory containing raw price JSON files.")
    parser.add_argument(
        "--weather-dir",
        default="data/raw/weather",
        help="Directory containing raw weather JSON files.",
    )
    parser.add_argument(
        "--mapping-dir",
        default="data/product_mapping",
        help="Directory containing product/category/group/unit mapping CSV files.",
    )
    parser.add_argument(
        "--output-root",
        default="data/processed",
        help="Root directory for clean_prices, clean_weather, and features outputs.",
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
    return parser


def main() -> int:
    args = build_parser().parse_args()
    required_feature_columns = [
        column.strip()
        for column in args.required_feature_columns.split(",")
        if column.strip()
    ]

    bundle = run_local_phase_b(
        price_dir=args.price_dir,
        weather_dir=args.weather_dir,
        mapping_dir=args.mapping_dir,
        output_root=args.output_root,
        config=TransformConfig(
            lags=parse_int_list(args.lags),
            rolling_windows=parse_int_list(args.rolling_windows),
            forward_fill_limit=args.forward_fill_limit,
            target_horizon_days=args.target_horizon_days,
        ),
        required_feature_columns=required_feature_columns or None,
    )

    summary = {
        "clean_prices_rows": int(len(bundle.clean_prices)),
        "clean_weather_rows": int(len(bundle.clean_weather)),
        "features_rows": int(len(bundle.features)),
        "output_root": str(Path(args.output_root).resolve()),
        "validation_status": bundle.validation_report["status"],
        "feature_columns": bundle.feature_schema["all_columns"],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
