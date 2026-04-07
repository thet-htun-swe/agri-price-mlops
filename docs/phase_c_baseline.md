# Phase C Baseline Training

Phase C trains one simple baseline model from the Phase B daily features dataset.

## Goal

Produce one working model artifact and one evaluation result for a single forecast target.

Default target:

- `target_next_day_price_coriander`

## Inputs

- Phase B features dataset at `data/processed/features/`

## Outputs

The training job writes three files under `artifacts/model/` by default:

- `model.pkl`
- `metrics.json`
- `training_summary.json`

## Training behavior

- Loads the Parquet features dataset and sorts by `date`.
- Uses a time-aware split with the latest rows held out for validation.
- Drops all target columns except the selected target.
- Trains a baseline `RandomForestRegressor` inside a median-imputation pipeline.
- Evaluates with `MAE` and `RMSE`.
- Saves the trained model plus metadata needed for downstream prediction.

## Local run

From the repo root:

```bash
python scripts/train_baseline_model.py \
  --features-path data/processed/features \
  --output-root artifacts/model \
  --target-column target_next_day_price_coriander
```

Optional knobs:

- `--validation-fraction 0.2`
- `--min-validation-rows 14`
- `--min-training-rows 30`
- `--n-estimators 200`
- `--max-depth 8`
- `--min-samples-leaf 2`
- `--random-state 42`

## Artifact contract

`model.pkl` stores:

- fitted sklearn pipeline
- selected feature column order
- target column
- model name
- training timestamp
- training config

`metrics.json` stores:

- `mae`
- `rmse`
- `train_rows`
- `validation_rows`

`training_summary.json` stores:

- model metadata
- target column
- feature columns
- train and validation date ranges
- config
- evaluation metrics
