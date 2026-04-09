from __future__ import annotations

import argparse
import json
import pickle
from pathlib import Path

from ml.training.phase_c_train_multi import (
    TrainingConfig,
    build_multi_target_metric_summary,
    load_features_dataset,
    predict_multi_output,
    prepare_modeling_frame,
    resolve_target_columns,
    split_time_aware_dataset,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate the trained SageMaker model and write an evaluation report.")
    parser.add_argument("--features-path", required=True)
    parser.add_argument("--model-path", required=True)
    parser.add_argument("--output-path", required=True)
    parser.add_argument("--target-columns", default="")
    parser.add_argument("--validation-fraction", type=float, default=0.2)
    parser.add_argument("--min-validation-rows", type=int, default=14)
    parser.add_argument("--min-training-rows", type=int, default=30)
    parser.add_argument("--random-state", type=int, default=42)
    parser.add_argument("--seasonal-period", type=int, default=7)
    parser.add_argument("--walk-forward-windows", type=int, default=3)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = TrainingConfig(
        validation_fraction=args.validation_fraction,
        min_validation_rows=args.min_validation_rows,
        min_training_rows=args.min_training_rows,
        random_state=args.random_state,
        seasonal_period=args.seasonal_period,
        walk_forward_windows=args.walk_forward_windows,
        target_columns=tuple(value.strip() for value in args.target_columns.split(",") if value.strip()),
    )

    features = load_features_dataset(args.features_path)
    target_columns = resolve_target_columns(features, config)
    frame = prepare_modeling_frame(features, target_columns)
    train_frame, validation_frame = split_time_aware_dataset(frame, config)

    feature_columns = [c for c in frame.columns if c not in ("date", *target_columns)]
    with Path(args.model_path).open("rb") as file_obj:
        artifact = pickle.load(file_obj)

    model = artifact["model"]
    predictions = predict_multi_output(model, validation_frame, feature_columns, target_columns)
    metrics = build_multi_target_metric_summary(validation_frame[list(target_columns)], predictions, len(train_frame), len(validation_frame))
    report = {
        "evaluation_type": "holdout",
        "target_columns": list(target_columns),
        "metrics": metrics,
        "feature_columns": feature_columns,
        "model_name": artifact.get("model_name"),
        "trained_at_utc": artifact.get("trained_at_utc"),
    }

    output_path = Path(args.output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
