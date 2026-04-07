from ml.training.phase_c_train_multi import *  # noqa: F401,F403

"""


@dataclass(frozen=True)
class TrainingConfig:
    target_column: str = DEFAULT_TARGET_COLUMN
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


@dataclass(frozen=True)
class TrainingArtifacts:
    model_path: str
    metrics_path: str
    summary_path: str
    comparison_report_path: str
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
    result = train_phase_c_models(features=features, config=config)
    write_training_outputs(result=result, output_root=output_root)
    output_path = Path(output_root)
    return TrainingArtifacts(
        model_path=str((output_path / "model.pkl").resolve()),
        metrics_path=str((output_path / "metrics.json").resolve()),
        summary_path=str((output_path / "training_summary.json").resolve()),
        comparison_report_path=str((output_path / "comparison_report.json").resolve()),
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


def train_phase_c_models(features: pd.DataFrame, config: TrainingConfig) -> dict[str, Any]:
    if config.target_column not in features.columns:
        raise PhaseCValidationError(f"Target column not found: {config.target_column}")

    modeling_frame = prepare_modeling_frame(features=features, target_column=config.target_column)
    feature_columns = [column for column in modeling_frame.columns if column not in ("date", config.target_column)]
    if not feature_columns:
        raise PhaseCValidationError("No feature columns available for training.")

    holdout_train, holdout_validation = split_time_aware_dataset(modeling_frame, config)
    walk_forward_splits = build_walk_forward_splits(modeling_frame, config)
    comparison_report = evaluate_models_with_walk_forward(
        feature_columns=feature_columns,
        walk_forward_splits=walk_forward_splits,
        config=config,
    )

    xgboost_model = fit_primary_model(
        train_frame=holdout_train,
        feature_columns=feature_columns,
        target_column=config.target_column,
        config=config,
    )
    holdout_predictions = pd.Series(
        xgboost_model.predict(holdout_validation[feature_columns]),
        index=holdout_validation.index,
        dtype="float64",
    )
    holdout_metrics = build_metric_summary(
        actual=holdout_validation[config.target_column],
        predicted=holdout_predictions,
        train_rows=len(holdout_train),
        validation_rows=len(holdout_validation),
    )

    final_model = fit_primary_model(
        train_frame=modeling_frame,
        feature_columns=feature_columns,
        target_column=config.target_column,
        config=config,
    )
    trained_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    summary = {
        "model_name": DEFAULT_MODEL_NAME,
        "algorithm": "xgboost.XGBRegressor",
        "trained_at_utc": trained_at,
        "target_column": config.target_column,
        "feature_columns": feature_columns,
        "training_date_range": build_date_range_summary(modeling_frame["date"]),
        "holdout_train_date_range": build_date_range_summary(holdout_train["date"]),
        "holdout_validation_date_range": build_date_range_summary(holdout_validation["date"]),
        "config": asdict(config),
        "metrics": holdout_metrics,
        "walk_forward_windows": len(walk_forward_splits),
        "comparison_report_file": "comparison_report.json",
    }
    artifact_payload = {
        "model": final_model,
        "target_column": config.target_column,
        "feature_columns": feature_columns,
        "model_name": DEFAULT_MODEL_NAME,
        "trained_at_utc": trained_at,
        "config": asdict(config),
        "comparison_report": comparison_report,
    }

    return {
        "artifact_payload": artifact_payload,
        "metrics": holdout_metrics,
        "summary": summary,
        "comparison_report": comparison_report,
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
        column
        for column in modeling_frame.columns
        if column not in ("date", target_column) and not pd.api.types.is_numeric_dtype(modeling_frame[column])
    ]
    if non_numeric_columns:
        raise PhaseCValidationError(
            "Non-numeric feature columns found after Phase B processing: "
            + ", ".join(sorted(non_numeric_columns))
        )

    return modeling_frame


def split_time_aware_dataset(features: pd.DataFrame, config: TrainingConfig) -> tuple[pd.DataFrame, pd.DataFrame]:
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


def build_walk_forward_splits(features: pd.DataFrame, config: TrainingConfig) -> list[tuple[pd.DataFrame, pd.DataFrame]]:
    splits: list[tuple[pd.DataFrame, pd.DataFrame]] = []
    total_rows = len(features)
    validation_rows = max(config.min_validation_rows, math.ceil(total_rows * config.validation_fraction))

    for window_index in range(config.walk_forward_windows, 0, -1):
        validation_end = total_rows - (window_index - 1) * validation_rows
        validation_start = validation_end - validation_rows
        if validation_start <= 0:
            continue

        train_frame = features.iloc[:validation_start].copy()
        validation_frame = features.iloc[validation_start:validation_end].copy()
        if len(train_frame) < config.min_training_rows or len(validation_frame) < config.min_validation_rows:
            continue
        if train_frame["date"].max() >= validation_frame["date"].min():
            continue

        splits.append((train_frame.reset_index(drop=True), validation_frame.reset_index(drop=True)))

    if not splits:
        raise PhaseCValidationError("Unable to construct any valid walk-forward evaluation windows.")

    return splits


def evaluate_models_with_walk_forward(
    *,
    feature_columns: list[str],
    walk_forward_splits: list[tuple[pd.DataFrame, pd.DataFrame]],
    config: TrainingConfig,
) -> dict[str, Any]:
    xgboost_folds: list[dict[str, Any]] = []
    persistence_folds: list[dict[str, Any]] = []
    seasonal_naive_folds: list[dict[str, Any]] = []

    for fold_number, (train_frame, validation_frame) in enumerate(walk_forward_splits, start=1):
        actual = validation_frame[config.target_column]

        xgboost_model = fit_primary_model(
            train_frame=train_frame,
            feature_columns=feature_columns,
            target_column=config.target_column,
            config=config,
        )
        xgboost_predictions = pd.Series(
            xgboost_model.predict(validation_frame[feature_columns]),
            index=validation_frame.index,
            dtype="float64",
        )
        xgboost_folds.append(
            {
                "fold": fold_number,
                **build_metric_summary(actual, xgboost_predictions, len(train_frame), len(validation_frame)),
                "train_date_range": build_date_range_summary(train_frame["date"]),
                "validation_date_range": build_date_range_summary(validation_frame["date"]),
            }
        )

        persistence_predictions = build_persistence_predictions(
            train_target=train_frame[config.target_column],
            validation_target=validation_frame[config.target_column],
        )
        persistence_folds.append(
            {
                "fold": fold_number,
                **build_metric_summary(actual, persistence_predictions, len(train_frame), len(validation_frame)),
                "train_date_range": build_date_range_summary(train_frame["date"]),
                "validation_date_range": build_date_range_summary(validation_frame["date"]),
            }
        )

        seasonal_predictions = build_seasonal_naive_predictions(
            train_target=train_frame[config.target_column],
            validation_target=validation_frame[config.target_column],
            seasonal_period=config.seasonal_period,
        )
        seasonal_naive_folds.append(
            {
                "fold": fold_number,
                **build_metric_summary(actual, seasonal_predictions, len(train_frame), len(validation_frame)),
                "train_date_range": build_date_range_summary(train_frame["date"]),
                "validation_date_range": build_date_range_summary(validation_frame["date"]),
            }
        )

    models = {
        "xgboost": summarize_fold_metrics(xgboost_folds),
        "persistence": summarize_fold_metrics(persistence_folds),
        "seasonal_naive": summarize_fold_metrics(seasonal_naive_folds),
    }
    ranked_models = sorted(
        (
            {
                "model_name": model_name,
                "mean_mae": metrics["mean_mae"],
                "mean_rmse": metrics["mean_rmse"],
            }
            for model_name, metrics in models.items()
        ),
        key=lambda item: (item["mean_mae"], item["mean_rmse"]),
    )

    return {
        "evaluation_type": "walk_forward",
        "target_column": config.target_column,
        "feature_count": len(feature_columns),
        "window_count": len(walk_forward_splits),
        "models": models,
        "ranking_by_mean_mae": ranked_models,
        "winner": ranked_models[0]["model_name"],
    }


def summarize_fold_metrics(folds: list[dict[str, Any]]) -> dict[str, Any]:
    mae_values = [fold["mae"] for fold in folds]
    rmse_values = [fold["rmse"] for fold in folds]
    return {
        "folds": folds,
        "mean_mae": float(sum(mae_values) / len(mae_values)),
        "mean_rmse": float(sum(rmse_values) / len(rmse_values)),
    }


def fit_primary_model(
    *,
    train_frame: pd.DataFrame,
    feature_columns: list[str],
    target_column: str,
    config: TrainingConfig,
):
    model = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="median")),
            ("regressor", create_primary_regressor(config)),
        ]
    )
    model.fit(train_frame[feature_columns], train_frame[target_column])
    return model


def create_primary_regressor(config: TrainingConfig):
    try:
        from xgboost import XGBRegressor
    except ImportError as exc:
        raise PhaseCValidationError(
            "xgboost is required for Phase C. Install dependencies from ml/training/requirements.txt."
        ) from exc

    return XGBRegressor(
        n_estimators=config.xgb_n_estimators,
        max_depth=config.xgb_max_depth,
        learning_rate=config.xgb_learning_rate,
        subsample=config.xgb_subsample,
        colsample_bytree=config.xgb_colsample_bytree,
        reg_lambda=config.xgb_reg_lambda,
        random_state=config.random_state,
        objective="reg:squarederror",
        n_jobs=1,
    )


def build_persistence_predictions(train_target: pd.Series, validation_target: pd.Series) -> pd.Series:
    history = pd.concat([train_target.reset_index(drop=True), validation_target.reset_index(drop=True)], ignore_index=True)
    validation_start = len(train_target)
    predictions = history.shift(1).iloc[validation_start:].reset_index(drop=True)
    predictions = predictions.fillna(train_target.iloc[-1])
    return pd.Series(predictions.to_numpy(), index=validation_target.index, dtype="float64")


def build_seasonal_naive_predictions(
    *,
    train_target: pd.Series,
    validation_target: pd.Series,
    seasonal_period: int,
) -> pd.Series:
    history = pd.concat([train_target.reset_index(drop=True), validation_target.reset_index(drop=True)], ignore_index=True)
    validation_start = len(train_target)
    predictions = history.shift(seasonal_period).iloc[validation_start:].reset_index(drop=True)
    if predictions.isna().any():
        fallback = build_persistence_predictions(train_target=train_target, validation_target=validation_target).reset_index(drop=True)
        predictions = predictions.fillna(fallback)
    return pd.Series(predictions.to_numpy(), index=validation_target.index, dtype="float64")


def build_metric_summary(
    actual: pd.Series,
    predicted: pd.Series,
    train_rows: int,
    validation_rows: int,
) -> dict[str, Any]:
    return {
        "mae": float(mean_absolute_error(actual, predicted)),
        "rmse": float(math.sqrt(mean_squared_error(actual, predicted))),
        "train_rows": int(train_rows),
        "validation_rows": int(validation_rows),
    }


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
    comparison_report_path = root_path / "comparison_report.json"

    with model_path.open("wb") as file_obj:
        pickle.dump(result["artifact_payload"], file_obj)

    metrics_path.write_text(json.dumps(result["metrics"], indent=2), encoding="utf-8")
    summary_path.write_text(json.dumps(result["summary"], indent=2), encoding="utf-8")
    comparison_report_path.write_text(json.dumps(result["comparison_report"], indent=2), encoding="utf-8")


def clear_managed_outputs(output_root: Path) -> None:
    for file_name in MANAGED_METADATA_FILES:
        path = output_root / file_name
        if path.exists():
            path.unlink()
"""
