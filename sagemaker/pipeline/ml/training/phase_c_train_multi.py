from __future__ import annotations

import json
import math
import pickle
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.metrics import mean_absolute_error, mean_squared_error
from sklearn.multioutput import MultiOutputRegressor
from sklearn.pipeline import Pipeline

DEFAULT_MODEL_NAME = "multi_output_xgboost"
TARGET_PREFIX = "target_next_day_"
MANAGED_METADATA_FILES = ("metrics.json", "training_summary.json", "comparison_report.json", "model.pkl")


class PhaseCValidationError(ValueError):
    pass


@dataclass(frozen=True)
class TrainingConfig:
    validation_fraction: float = 0.2
    min_validation_rows: int = 14
    min_training_rows: int = 30
    random_state: int = 42
    seasonal_period: int = 7
    walk_forward_windows: int = 3
    xgb_n_estimators: int = 300
    xgb_max_depth: int = 6
    xgb_learning_rate: float = 0.05
    xgb_subsample: float = 0.9
    xgb_colsample_bytree: float = 0.9
    xgb_reg_lambda: float = 1.0
    target_columns: tuple[str, ...] = ()


@dataclass(frozen=True)
class TrainingArtifacts:
    model_path: str
    metrics_path: str
    summary_path: str
    comparison_report_path: str
    metrics: dict[str, Any]
    summary: dict[str, Any]


def run_local_phase_c(features_path: str | Path, output_root: str | Path, config: TrainingConfig | None = None) -> TrainingArtifacts:
    config = config or TrainingConfig()
    features = load_features_dataset(features_path)
    result = train_phase_c_models(features, config)
    write_training_outputs(result, output_root)
    root = Path(output_root)
    return TrainingArtifacts(
        model_path=str((root / "model.pkl").resolve()),
        metrics_path=str((root / "metrics.json").resolve()),
        summary_path=str((root / "training_summary.json").resolve()),
        comparison_report_path=str((root / "comparison_report.json").resolve()),
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


def resolve_target_columns(features: pd.DataFrame, config: TrainingConfig) -> tuple[str, ...]:
    requested = tuple(c for c in config.target_columns if c)
    if requested:
        missing = [c for c in requested if c not in features.columns]
        if missing:
            raise PhaseCValidationError("Requested target columns not found: " + ", ".join(sorted(missing)))
        return requested
    found = tuple(c for c in features.columns if c.startswith(TARGET_PREFIX))
    if not found:
        raise PhaseCValidationError("No target columns found in the features dataset.")
    return found


def prepare_modeling_frame(features: pd.DataFrame, target_columns: tuple[str, ...]) -> pd.DataFrame:
    frame = features.copy().dropna(subset=list(target_columns)).reset_index(drop=True)
    if frame.empty:
        raise PhaseCValidationError("No rows with non-null target values for the selected target columns.")

    feature_columns = [c for c in frame.columns if c not in ("date", *target_columns)]
    for column in feature_columns:
        if pd.api.types.is_categorical_dtype(frame[column]) or pd.api.types.is_object_dtype(frame[column]):
            frame[column] = pd.to_numeric(frame[column], errors="coerce")

    bad = [c for c in feature_columns if not pd.api.types.is_numeric_dtype(frame[c])]
    if bad:
        raise PhaseCValidationError("Non-numeric feature columns found after Phase B processing: " + ", ".join(sorted(bad)))
    return frame


def split_time_aware_dataset(features: pd.DataFrame, config: TrainingConfig) -> tuple[pd.DataFrame, pd.DataFrame]:
    if len(features) < config.min_training_rows + config.min_validation_rows:
        raise PhaseCValidationError(f"Not enough rows for time-aware split: need at least {config.min_training_rows + config.min_validation_rows}, got {len(features)}.")
    validation_rows = max(config.min_validation_rows, math.ceil(len(features) * config.validation_fraction))
    validation_rows = min(validation_rows, len(features) - config.min_training_rows)
    split_index = len(features) - validation_rows
    train_frame = features.iloc[:split_index].copy()
    validation_frame = features.iloc[split_index:].copy()
    if len(train_frame) < config.min_training_rows or len(validation_frame) < config.min_validation_rows:
        raise PhaseCValidationError("Invalid train/validation split sizes.")
    if train_frame["date"].max() >= validation_frame["date"].min():
        raise PhaseCValidationError("Time-aware split is invalid because train dates overlap validation dates.")
    return train_frame.reset_index(drop=True), validation_frame.reset_index(drop=True)


def build_walk_forward_splits(features: pd.DataFrame, config: TrainingConfig) -> list[tuple[pd.DataFrame, pd.DataFrame]]:
    splits: list[tuple[pd.DataFrame, pd.DataFrame]] = []
    validation_rows = max(config.min_validation_rows, math.ceil(len(features) * config.validation_fraction))
    for window_index in range(config.walk_forward_windows, 0, -1):
        end = len(features) - (window_index - 1) * validation_rows
        start = end - validation_rows
        if start <= 0:
            continue
        train_frame = features.iloc[:start].copy()
        validation_frame = features.iloc[start:end].copy()
        if len(train_frame) < config.min_training_rows or len(validation_frame) < config.min_validation_rows:
            continue
        if train_frame["date"].max() >= validation_frame["date"].min():
            continue
        splits.append((train_frame.reset_index(drop=True), validation_frame.reset_index(drop=True)))
    if not splits:
        raise PhaseCValidationError("Unable to construct any valid walk-forward evaluation windows.")
    return splits


def create_primary_regressor(config: TrainingConfig):
    try:
        from xgboost import XGBRegressor
    except ImportError as exc:
        raise PhaseCValidationError("xgboost is required for Phase C. Install dependencies from ml/training/requirements.txt.") from exc
    return MultiOutputRegressor(
        XGBRegressor(
            n_estimators=config.xgb_n_estimators,
            max_depth=config.xgb_max_depth,
            learning_rate=config.xgb_learning_rate,
            subsample=config.xgb_subsample,
            colsample_bytree=config.xgb_colsample_bytree,
            reg_lambda=config.xgb_reg_lambda,
            random_state=config.random_state,
            objective="reg:squarederror",
            n_jobs=1,
        ),
        n_jobs=1,
    )


def fit_primary_model(train_frame: pd.DataFrame, feature_columns: list[str], target_columns: tuple[str, ...], config: TrainingConfig):
    model = Pipeline([("imputer", SimpleImputer(strategy="median")), ("regressor", create_primary_regressor(config))])
    model.fit(train_frame[feature_columns], train_frame[list(target_columns)])
    return model


def predict_multi_output(model, frame: pd.DataFrame, feature_columns: list[str], target_columns: tuple[str, ...]) -> pd.DataFrame:
    return pd.DataFrame(model.predict(frame[feature_columns]), columns=list(target_columns), index=frame.index)


def build_persistence_predictions(train_frame: pd.DataFrame, validation_frame: pd.DataFrame, target_columns: tuple[str, ...]) -> pd.DataFrame:
    out = {}
    for column in target_columns:
        history = pd.concat([train_frame[column].reset_index(drop=True), validation_frame[column].reset_index(drop=True)], ignore_index=True)
        predicted = history.shift(1).iloc[len(train_frame):].reset_index(drop=True).fillna(train_frame[column].iloc[-1])
        out[column] = pd.Series(predicted.to_numpy(), index=validation_frame.index, dtype="float64")
    return pd.DataFrame(out, index=validation_frame.index)


def build_seasonal_naive_predictions(train_frame: pd.DataFrame, validation_frame: pd.DataFrame, target_columns: tuple[str, ...], seasonal_period: int) -> pd.DataFrame:
    fallback = build_persistence_predictions(train_frame, validation_frame, target_columns)
    out = {}
    for column in target_columns:
        history = pd.concat([train_frame[column].reset_index(drop=True), validation_frame[column].reset_index(drop=True)], ignore_index=True)
        predicted = history.shift(seasonal_period).iloc[len(train_frame):].reset_index(drop=True).fillna(fallback[column].reset_index(drop=True))
        out[column] = pd.Series(predicted.to_numpy(), index=validation_frame.index, dtype="float64")
    return pd.DataFrame(out, index=validation_frame.index)


def build_multi_target_metric_summary(actual_frame: pd.DataFrame, predicted_frame: pd.DataFrame, train_rows: int, validation_rows: int) -> dict[str, Any]:
    by_target = {}
    maes: list[float] = []
    rmses: list[float] = []
    for column in actual_frame.columns:
        mae = float(mean_absolute_error(actual_frame[column], predicted_frame[column]))
        rmse = float(math.sqrt(mean_squared_error(actual_frame[column], predicted_frame[column])))
        maes.append(mae)
        rmses.append(rmse)
        by_target[column] = {"mae": mae, "rmse": rmse}
    return {"overall": {"mae": float(sum(maes) / len(maes)), "rmse": float(sum(rmses) / len(rmses))}, "by_target": by_target, "train_rows": int(train_rows), "validation_rows": int(validation_rows)}


def summarize_multi_target_fold_metrics(folds: list[dict[str, Any]], target_columns: tuple[str, ...]) -> dict[str, Any]:
    by_target = {}
    for column in target_columns:
        maes = [fold["by_target"][column]["mae"] for fold in folds]
        rmses = [fold["by_target"][column]["rmse"] for fold in folds]
        by_target[column] = {"mean_mae": float(sum(maes) / len(maes)), "mean_rmse": float(sum(rmses) / len(rmses))}
    overall_mae = [fold["overall"]["mae"] for fold in folds]
    overall_rmse = [fold["overall"]["rmse"] for fold in folds]
    return {"folds": folds, "overall": {"mean_mae": float(sum(overall_mae) / len(overall_mae)), "mean_rmse": float(sum(overall_rmse) / len(overall_rmse))}, "by_target": by_target}


def evaluate_models_with_walk_forward(target_columns: tuple[str, ...], feature_columns: list[str], splits: list[tuple[pd.DataFrame, pd.DataFrame]], config: TrainingConfig) -> dict[str, Any]:
    xgb_folds: list[dict[str, Any]] = []
    persistence_folds: list[dict[str, Any]] = []
    seasonal_folds: list[dict[str, Any]] = []
    for fold_number, (train_frame, validation_frame) in enumerate(splits, start=1):
        xgb = predict_multi_output(fit_primary_model(train_frame, feature_columns, target_columns, config), validation_frame, feature_columns, target_columns)
        persistence = build_persistence_predictions(train_frame, validation_frame, target_columns)
        seasonal = build_seasonal_naive_predictions(train_frame, validation_frame, target_columns, config.seasonal_period)
        xgb_folds.append({"fold": fold_number, **build_multi_target_metric_summary(validation_frame[list(target_columns)], xgb, len(train_frame), len(validation_frame))})
        persistence_folds.append({"fold": fold_number, **build_multi_target_metric_summary(validation_frame[list(target_columns)], persistence, len(train_frame), len(validation_frame))})
        seasonal_folds.append({"fold": fold_number, **build_multi_target_metric_summary(validation_frame[list(target_columns)], seasonal, len(train_frame), len(validation_frame))})
    models = {
        "xgboost": summarize_multi_target_fold_metrics(xgb_folds, target_columns),
        "persistence": summarize_multi_target_fold_metrics(persistence_folds, target_columns),
        "seasonal_naive": summarize_multi_target_fold_metrics(seasonal_folds, target_columns),
    }
    ranking = sorted(({"model_name": n, "mean_mae": d["overall"]["mean_mae"], "mean_rmse": d["overall"]["mean_rmse"]} for n, d in models.items()), key=lambda item: (item["mean_mae"], item["mean_rmse"]))
    return {"evaluation_type": "walk_forward", "target_columns": list(target_columns), "feature_count": len(feature_columns), "window_count": len(splits), "models": models, "ranking_by_mean_mae": ranking, "winner": ranking[0]["model_name"]}


def train_phase_c_models(features: pd.DataFrame, config: TrainingConfig) -> dict[str, Any]:
    target_columns = resolve_target_columns(features, config)
    frame = prepare_modeling_frame(features, target_columns)
    feature_columns = [c for c in frame.columns if c not in ("date", *target_columns)]
    train_frame, validation_frame = split_time_aware_dataset(frame, config)
    splits = build_walk_forward_splits(frame, config)
    comparison_report = evaluate_models_with_walk_forward(target_columns, feature_columns, splits, config)
    holdout_model = fit_primary_model(train_frame, feature_columns, target_columns, config)
    holdout_predictions = predict_multi_output(holdout_model, validation_frame, feature_columns, target_columns)
    holdout_metrics = build_multi_target_metric_summary(validation_frame[list(target_columns)], holdout_predictions, len(train_frame), len(validation_frame))
    final_model = fit_primary_model(frame, feature_columns, target_columns, config)
    trained_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    summary = {"model_name": DEFAULT_MODEL_NAME, "algorithm": "sklearn.multioutput.MultiOutputRegressor(xgboost.XGBRegressor)", "trained_at_utc": trained_at, "target_columns": list(target_columns), "feature_columns": feature_columns, "training_date_range": build_date_range_summary(frame["date"]), "holdout_train_date_range": build_date_range_summary(train_frame["date"]), "holdout_validation_date_range": build_date_range_summary(validation_frame["date"]), "config": asdict(config), "metrics": holdout_metrics, "walk_forward_windows": len(splits), "comparison_report_file": "comparison_report.json"}
    artifact = {"model": final_model, "target_columns": list(target_columns), "feature_columns": feature_columns, "model_name": DEFAULT_MODEL_NAME, "trained_at_utc": trained_at, "config": asdict(config), "comparison_report": comparison_report}
    return {"artifact_payload": artifact, "metrics": holdout_metrics, "summary": summary, "comparison_report": comparison_report}


def build_date_range_summary(series: pd.Series) -> dict[str, str]:
    return {"start_date": pd.Timestamp(series.min()).strftime("%Y-%m-%d"), "end_date": pd.Timestamp(series.max()).strftime("%Y-%m-%d")}


def write_training_outputs(result: dict[str, Any], output_root: str | Path) -> None:
    root = Path(output_root)
    root.mkdir(parents=True, exist_ok=True)
    clear_managed_outputs(root)
    with (root / "model.pkl").open("wb") as file_obj:
        pickle.dump(result["artifact_payload"], file_obj)
    (root / "metrics.json").write_text(json.dumps(result["metrics"], indent=2), encoding="utf-8")
    (root / "training_summary.json").write_text(json.dumps(result["summary"], indent=2), encoding="utf-8")
    (root / "comparison_report.json").write_text(json.dumps(result["comparison_report"], indent=2), encoding="utf-8")


def clear_managed_outputs(output_root: Path) -> None:
    for file_name in MANAGED_METADATA_FILES:
        path = output_root / file_name
        if path.exists():
            path.unlink()
