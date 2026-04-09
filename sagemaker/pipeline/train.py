from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from ml.training.phase_c_train_multi import (
    TrainingConfig,
    load_features_dataset,
    train_phase_c_models,
    write_training_outputs,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train the multi-output agricultural price model inside SageMaker.")
    parser.add_argument("--features-path", default=os.environ.get("SM_CHANNEL_TRAINING", "/opt/ml/input/data/training"))
    parser.add_argument("--model-dir", default=os.environ.get("SM_MODEL_DIR", "/opt/ml/model"))
    parser.add_argument("--output-data-dir", default=os.environ.get("SM_OUTPUT_DATA_DIR", "/opt/ml/output/data"))
    parser.add_argument("--target-columns", default="")
    parser.add_argument("--validation-fraction", type=float, default=0.2)
    parser.add_argument("--min-validation-rows", type=int, default=14)
    parser.add_argument("--min-training-rows", type=int, default=30)
    parser.add_argument("--walk-forward-windows", type=int, default=3)
    parser.add_argument("--seasonal-period", type=int, default=7)
    parser.add_argument("--xgb-n-estimators", type=int, default=300)
    parser.add_argument("--xgb-max-depth", type=int, default=6)
    parser.add_argument("--xgb-learning-rate", type=float, default=0.05)
    parser.add_argument("--xgb-subsample", type=float, default=0.9)
    parser.add_argument("--xgb-colsample-bytree", type=float, default=0.9)
    parser.add_argument("--xgb-reg-lambda", type=float, default=1.0)
    parser.add_argument("--random-state", type=int, default=42)
    return parser.parse_args()


def resolve_features_path(raw_path: str) -> Path:
    path = Path(raw_path)
    if path.is_file():
        return path
    parquet_candidates = sorted(path.rglob("*.parquet"))
    if parquet_candidates:
        return path
    if path.exists():
        return path
    raise FileNotFoundError(f"Features path does not exist: {path}")


def build_config(args: argparse.Namespace) -> TrainingConfig:
    target_columns = tuple(value.strip() for value in args.target_columns.split(",") if value.strip())
    return TrainingConfig(
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
    )


def main() -> None:
    args = parse_args()
    features_path = resolve_features_path(args.features_path)
    config = build_config(args)

    features = load_features_dataset(features_path)
    result = train_phase_c_models(features, config)

    model_dir = Path(args.model_dir)
    model_dir.mkdir(parents=True, exist_ok=True)
    write_training_outputs(result, model_dir)

    output_dir = Path(args.output_data_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    training_report = {
        "model_dir": str(model_dir),
        "features_path": str(features_path),
        "summary": result["summary"],
        "metrics": result["metrics"],
        "comparison_report": result["comparison_report"],
    }
    (output_dir / "training_report.json").write_text(json.dumps(training_report, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
