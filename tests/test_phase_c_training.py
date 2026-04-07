from __future__ import annotations

import json
import pickle
from pathlib import Path

import pandas as pd

from ml.training.phase_c_train import TrainingConfig, run_local_phase_c, split_time_aware_dataset


def test_phase_c_trains_and_writes_artifacts(tmp_path: Path) -> None:
    features_dir = tmp_path / "features"
    features_file = features_dir / "part-000.parquet"
    output_dir = tmp_path / "artifacts" / "model"
    features_dir.mkdir(parents=True)

    features = build_synthetic_features(row_count=80)
    features.to_parquet(features_file, index=False)

    artifacts = run_local_phase_c(
        features_path=features_dir,
        output_root=output_dir,
        config=TrainingConfig(
            target_column="target_next_day_price_coriander",
            validation_fraction=0.25,
            min_validation_rows=14,
            min_training_rows=30,
            random_state=7,
            n_estimators=50,
            max_depth=5,
            min_samples_leaf=1,
        ),
    )

    assert Path(artifacts.model_path).exists()
    assert Path(artifacts.metrics_path).exists()
    assert Path(artifacts.summary_path).exists()
    assert artifacts.metrics["train_rows"] == 60
    assert artifacts.metrics["validation_rows"] == 20
    assert artifacts.summary["target_column"] == "target_next_day_price_coriander"

    metrics_payload = json.loads(Path(artifacts.metrics_path).read_text(encoding="utf-8"))
    summary_payload = json.loads(Path(artifacts.summary_path).read_text(encoding="utf-8"))
    model_payload = pickle.loads(Path(artifacts.model_path).read_bytes())

    assert set(metrics_payload) == {"mae", "rmse", "train_rows", "validation_rows"}
    assert summary_payload["model_name"] == "baseline_random_forest"
    assert summary_payload["train_date_range"]["end_date"] < summary_payload["validation_date_range"]["start_date"]
    assert "price_coriander" in summary_payload["feature_columns"]
    assert model_payload["target_column"] == "target_next_day_price_coriander"
    assert "feature_columns" in model_payload
    assert "model" in model_payload


def test_phase_c_split_is_strictly_chronological() -> None:
    frame = build_synthetic_features(row_count=50)

    train_frame, validation_frame = split_time_aware_dataset(
        frame,
        TrainingConfig(
            target_column="target_next_day_price_coriander",
            validation_fraction=0.2,
            min_validation_rows=10,
            min_training_rows=20,
        ),
    )

    assert len(train_frame) == 40
    assert len(validation_frame) == 10
    assert train_frame["date"].max() < validation_frame["date"].min()


def build_synthetic_features(row_count: int) -> pd.DataFrame:
    dates = pd.date_range("2025-01-01", periods=row_count, freq="D")
    base_price = pd.Series(range(row_count), dtype="float64") + 100.0

    frame = pd.DataFrame(
        {
            "date": dates,
            "temperature_2m_mean": 30.0 + (base_price % 5),
            "precipitation_sum": (base_price % 3),
            "relative_humidity_2m_mean": 70.0 + (base_price % 10),
            "price_coriander": base_price,
            "price_kale": base_price + 5.0,
            "price_coriander_lag_1": base_price.shift(1),
            "price_coriander_rolling_mean_3": base_price.rolling(3, min_periods=1).mean(),
            "year": dates.year.astype("int32"),
            "month": dates.month.astype("int32"),
            "day_of_month": dates.day.astype("int32"),
            "day_of_week": dates.dayofweek.astype("int32"),
            "week_of_year": dates.isocalendar().week.astype("int32"),
            "day_of_year": dates.dayofyear.astype("int32"),
            "quarter": dates.quarter.astype("int32"),
            "is_weekend": dates.dayofweek.isin([5, 6]).astype("int8"),
        }
    )
    frame["target_next_day_price_coriander"] = frame["price_coriander"] + 1.0
    frame.loc[0, "price_coriander_lag_1"] = pd.NA
    return frame
