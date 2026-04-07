from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ml.training.phase_c_train import DEFAULT_TARGET_COLUMN, TrainingConfig, run_local_phase_c


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Train the Phase C baseline model from processed features.")
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
    parser.add_argument(
        "--target-column",
        default=DEFAULT_TARGET_COLUMN,
        help="Target column to train against.",
    )
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
    parser.add_argument("--n-estimators", type=int, default=200, help="Random forest tree count.")
    parser.add_argument("--max-depth", type=int, default=8, help="Random forest max depth.")
    parser.add_argument("--min-samples-leaf", type=int, default=2, help="Random forest minimum samples per leaf.")
    parser.add_argument("--random-state", type=int, default=42, help="Random seed for reproducible training.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    artifacts = run_local_phase_c(
        features_path=args.features_path,
        output_root=args.output_root,
        target_column=args.target_column,
        config=TrainingConfig(
            target_column=args.target_column,
            validation_fraction=args.validation_fraction,
            min_validation_rows=args.min_validation_rows,
            min_training_rows=args.min_training_rows,
            n_estimators=args.n_estimators,
            max_depth=args.max_depth,
            min_samples_leaf=args.min_samples_leaf,
            random_state=args.random_state,
        ),
    )

    summary = {
        "model_path": artifacts.model_path,
        "metrics_path": artifacts.metrics_path,
        "summary_path": artifacts.summary_path,
        "target_column": artifacts.summary["target_column"],
        "metrics": artifacts.metrics,
    }
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
