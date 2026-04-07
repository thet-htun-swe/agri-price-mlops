from __future__ import annotations

import json
import math
import pickle
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.metrics import mean_absolute_error, mean_squared_error
from sklearn.pipeline import Pipeline


DEFAULT_TARGET_COLUMN = "target_next_day_price_coriander"
DEFAULT_MODEL_NAME = "baseline_random_forest"
MANAGED_METADATA_FILES = ("metrics.json", "training_summary.json", "model.pkl")


class PhaseCValidationError(ValueError):
    """Raised when the Phase C training flow cannot proceed safely."""


@dataclass(frozen=True)
class TrainingConfig:
    target_column: str = DEFAULT_TARGET_COLUMN
    validation_fraction: float = 0.2
    min_validation_rows: int = 14
    min_training_rows: int = 30
    random_state: int = 42
    n_estimators: int = 200
    max_depth: int | None = 8
    min_samples_leaf: int = 2


@dataclass(frozen=True)
class TrainingArtifacts:
    model_path: str
    metrics_path: str
    summary_path: str
    metrics: dict[str, Any]
    summary: dict[str, Any]


def run_local_phase_c(
    features_path: str | Path,
    output_root: str | Path,
    target_column: str = DEFAULT_TARGET_COLUMN,
    config: TrainingConfig | None = None,
) -> TrainingArtifacts:
    config = config or TrainingConfig(target_column=target_column)
    features = load_features_dataset(features_path)
    result = train_baseline_model(features=features, config=config)
    write_training_outputs(result=result, output_root=output_root)
    return TrainingArtifacts(
        model_path=str((Path(output_root) / "model.pkl").resolve()),
        metrics_path=str((Path(output_root) / "metrics.json").resolve()),
        summary_path=str((Path(output_root) / "training_summary.json").resolve()),
        metrics=result["metrics"],
        summary=result["summary"],
    )


def load_features_dataset(features_path: str | Path) -> pd.DataFrame:
    path = Path(features_path)
    if not path.exists():
        raise PhaseCValidationError(f"Features dataset does not exist: {path}")

    features = pd.read_parquet(path)
    if "date" not in features.columns:
        raise PhaseCValidationError("Features dataset must include a date column.")

    features = features.copy()
    features["date"] = pd.to_datetime(features["date"], errors="coerce")
    features = features.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)

    if features.empty:
        raise PhaseCValidationError("Features dataset is empty after loading.")

    return features


def train_baseline_model(
    features: pd.DataFrame,
    config: TrainingConfig,
) -> dict[str, Any]:
    if config.target_column not in features.columns:
        raise PhaseCValidationError(f"Target column not found: {config.target_column}")

    modeling_frame = prepare_modeling_frame(features=features, target_column=config.target_column)
    train_frame, validation_frame = split_time_aware_dataset(modeling_frame, config)

    feature_columns = [column for column in train_frame.columns if column not in ("date", config.target_column)]
    if not feature_columns:
        raise PhaseCValidationError("No feature columns available for training.")

    model = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="median")),
            (
                "regressor",
                RandomForestRegressor(
                    n_estimators=config.n_estimators,
                    max_depth=config.max_depth,
                    min_samples_leaf=config.min_samples_leaf,
                    random_state=config.random_state,
                ),
            ),
        ]
    )

    x_train = train_frame[feature_columns]
    y_train = train_frame[config.target_column]
    x_validation = validation_frame[feature_columns]
    y_validation = validation_frame[config.target_column]

    model.fit(x_train, y_train)
    validation_predictions = model.predict(x_validation)

    metrics = {
        "mae": float(mean_absolute_error(y_validation, validation_predictions)),
        "rmse": float(math.sqrt(mean_squared_error(y_validation, validation_predictions))),
        "train_rows": int(len(train_frame)),
        "validation_rows": int(len(validation_frame)),
    }

    summary = {
        "model_name": DEFAULT_MODEL_NAME,
        "algorithm": "sklearn.ensemble.RandomForestRegressor",
        "trained_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "target_column": config.target_column,
        "feature_columns": feature_columns,
        "train_date_range": build_date_range_summary(train_frame["date"]),
        "validation_date_range": build_date_range_summary(validation_frame["date"]),
        "config": asdict(config),
        "metrics": metrics,
    }

    artifact_payload = {
        "model": model,
        "target_column": config.target_column,
        "feature_columns": feature_columns,
        "model_name": DEFAULT_MODEL_NAME,
        "trained_at_utc": summary["trained_at_utc"],
        "config": asdict(config),
    }

    return {
        "artifact_payload": artifact_payload,
        "metrics": metrics,
        "summary": summary,
    }


def prepare_modeling_frame(features: pd.DataFrame, target_column: str) -> pd.DataFrame:
    modeling_frame = features.copy()
    target_columns = [column for column in modeling_frame.columns if column.startswith("target_next_day_")]
    columns_to_drop = [column for column in target_columns if column != target_column]
    if columns_to_drop:
        modeling_frame = modeling_frame.drop(columns=columns_to_drop)

    modeling_frame = modeling_frame.dropna(subset=[target_column]).reset_index(drop=True)
    if modeling_frame.empty:
        raise PhaseCValidationError(f"No rows with non-null target values for {target_column}.")

    non_numeric_columns = [
        column for column in modeling_frame.columns if column not in ("date", target_column) and not pd.api.types.is_numeric_dtype(modeling_frame[column])
    ]
    if non_numeric_columns:
        raise PhaseCValidationError(
            "Non-numeric feature columns found after Phase B processing: "
            + ", ".join(sorted(non_numeric_columns))
        )

    return modeling_frame


def split_time_aware_dataset(
    features: pd.DataFrame,
    config: TrainingConfig,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    if len(features) < config.min_training_rows + config.min_validation_rows:
        raise PhaseCValidationError(
            "Not enough rows for time-aware split: "
            f"need at least {config.min_training_rows + config.min_validation_rows}, got {len(features)}."
        )

    validation_rows = max(config.min_validation_rows, math.ceil(len(features) * config.validation_fraction))
    validation_rows = min(validation_rows, len(features) - config.min_training_rows)
    split_index = len(features) - validation_rows

    train_frame = features.iloc[:split_index].copy()
    validation_frame = features.iloc[split_index:].copy()

    if len(train_frame) < config.min_training_rows:
        raise PhaseCValidationError(
            f"Training split is too small: expected at least {config.min_training_rows}, got {len(train_frame)}."
        )
    if len(validation_frame) < config.min_validation_rows:
        raise PhaseCValidationError(
            f"Validation split is too small: expected at least {config.min_validation_rows}, got {len(validation_frame)}."
        )
    if train_frame["date"].max() >= validation_frame["date"].min():
        raise PhaseCValidationError("Time-aware split is invalid because train dates overlap validation dates.")

    return train_frame.reset_index(drop=True), validation_frame.reset_index(drop=True)


def build_date_range_summary(series: pd.Series) -> dict[str, str]:
    return {
        "start_date": pd.Timestamp(series.min()).strftime("%Y-%m-%d"),
        "end_date": pd.Timestamp(series.max()).strftime("%Y-%m-%d"),
    }


def write_training_outputs(result: dict[str, Any], output_root: str | Path) -> None:
    root_path = Path(output_root)
    root_path.mkdir(parents=True, exist_ok=True)
    clear_managed_outputs(root_path)

    model_path = root_path / "model.pkl"
    metrics_path = root_path / "metrics.json"
    summary_path = root_path / "training_summary.json"

    with model_path.open("wb") as file_obj:
        pickle.dump(result["artifact_payload"], file_obj)

    metrics_path.write_text(json.dumps(result["metrics"], indent=2), encoding="utf-8")
    summary_path.write_text(json.dumps(result["summary"], indent=2), encoding="utf-8")


def clear_managed_outputs(output_root: Path) -> None:
    for file_name in MANAGED_METADATA_FILES:
        path = output_root / file_name
        if path.exists():
            path.unlink()
