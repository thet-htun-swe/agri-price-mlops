from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ml.training.phase_c_train_multi import TrainingConfig, run_local_phase_c


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Train and evaluate the Phase C forecasting models from processed features.")
    parser.add_argument(
        "--features-path",
        default="data/processed/features",
        help="Path to the Phase B features Parquet dataset.",
    )
    parser.add_argument(
        "--output-root",
        default="artifacts/model",
        help="Directory for the trained model artifact and evaluation outputs.",
    )
    parser.add_argument("--target-columns", default="", help="Optional comma-separated target columns. Defaults to all target_next_day_* columns.")
    parser.add_argument(
        "--validation-fraction",
        type=float,
        default=0.2,
        help="Fraction of the chronologically latest rows reserved for validation.",
    )
    parser.add_argument(
        "--min-validation-rows",
        type=int,
        default=14,
        help="Minimum number of validation rows in the time-aware split.",
    )
    parser.add_argument(
        "--min-training-rows",
        type=int,
        default=30,
        help="Minimum number of training rows in the time-aware split.",
    )
    parser.add_argument("--walk-forward-windows", type=int, default=3, help="Number of walk-forward validation windows.")
    parser.add_argument("--seasonal-period", type=int, default=7, help="Seasonal naive baseline lag in days.")
    parser.add_argument("--xgb-n-estimators", type=int, default=300, help="XGBoost estimator count.")
    parser.add_argument("--xgb-max-depth", type=int, default=6, help="XGBoost max depth.")
    parser.add_argument("--xgb-learning-rate", type=float, default=0.05, help="XGBoost learning rate.")
    parser.add_argument("--xgb-subsample", type=float, default=0.9, help="XGBoost subsample ratio.")
    parser.add_argument("--xgb-colsample-bytree", type=float, default=0.9, help="XGBoost feature subsample ratio.")
    parser.add_argument("--xgb-reg-lambda", type=float, default=1.0, help="XGBoost L2 regularization.")
    parser.add_argument("--random-state", type=int, default=42, help="Random seed for reproducible training.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    target_columns = tuple(column.strip() for column in args.target_columns.split(",") if column.strip())
    artifacts = run_local_phase_c(
        features_path=args.features_path,
        output_root=args.output_root,
        config=TrainingConfig(
            validation_fraction=args.validation_fraction,
            min_validation_rows=args.min_validation_rows,
            min_training_rows=args.min_training_rows,
            walk_forward_windows=args.walk_forward_windows,
            seasonal_period=args.seasonal_period,
            xgb_n_estimators=args.xgb_n_estimators,
            xgb_max_depth=args.xgb_max_depth,
            xgb_learning_rate=args.xgb_learning_rate,
            xgb_subsample=args.xgb_subsample,
            xgb_colsample_bytree=args.xgb_colsample_bytree,
            xgb_reg_lambda=args.xgb_reg_lambda,
            random_state=args.random_state,
            target_columns=target_columns,
        ),
    )

    summary = {
        "model_path": artifacts.model_path,
        "metrics_path": artifacts.metrics_path,
        "summary_path": artifacts.summary_path,
        "comparison_report_path": artifacts.comparison_report_path,
        "target_columns": artifacts.summary["target_columns"],
        "metrics": artifacts.metrics,
    }
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
