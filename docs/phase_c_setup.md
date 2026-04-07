# Phase C Setup

This guide covers the current multi-output Phase C implementation in this repo.

Phase C is implemented as:

- training module: [phase_c_train.py](D:/AIT/MLOps/project/repos/agri-price-mlops/ml/training/phase_c_train.py)
- local runner: [train_baseline_model.py](D:/AIT/MLOps/project/repos/agri-price-mlops/scripts/train_baseline_model.py)

The current primary model is:

- `sklearn.multioutput.MultiOutputRegressor(xgboost.XGBRegressor)`

The current baseline comparisons are:

- persistence
- seasonal naive

Phase C now trains one artifact that predicts multiple product targets together, evaluates with walk-forward validation, and writes a comparison report alongside the final trained artifact.

## 1. Goal

Train and evaluate one multi-output forecasting model from the Phase B `features` dataset using:

- walk-forward validation
- Multi-output XGBoost as the primary model
- persistence and seasonal-naive baseline comparisons

## 2. Inputs

Phase C expects the Phase B features dataset to already exist.

Default input path:

```text
data/processed/features
```

The features dataset must include:

- `date`
- one or more target columns such as `target_next_day_price_coriander`
- numeric feature columns only, except for `date`

## 3. Outputs

Default output path:

```text
artifacts/model
```

Phase C writes:

- `model.pkl`
- `metrics.json`
- `training_summary.json`
- `comparison_report.json`

## 4. Install Requirements

Install the training dependencies listed in [requirements.txt](D:/AIT/MLOps/project/repos/agri-price-mlops/ml/training/requirements.txt):

```bash
pip install -r ml/training/requirements.txt
```

Required packages:

- `pandas`
- `pyarrow`
- `scikit-learn`
- `xgboost`

## 5. Default Training Flow

From the repo root, run:

```bash
python scripts/train_baseline_model.py \
  --features-path data/processed/features \
  --output-root artifacts/model
```

This uses the default target column:

```text
target_next_day_price_coriander
```

## 6. Choose the Target Columns

The current training code supports multiple target columns in one run.

Examples:

- `target_next_day_price_coriander`
- `target_next_day_price_kale`
- `target_next_day_price_lime`

To train a chosen subset:

```bash
python scripts/train_baseline_model.py \
  --features-path data/processed/features \
  --output-root artifacts/model \
  --target-columns target_next_day_price_coriander,target_next_day_price_kale
```

If you omit `--target-columns`, the trainer uses all `target_next_day_*` columns it finds.

## 7. Time-Aware Validation Rules

Phase C uses two evaluation layers:

- a walk-forward evaluation across multiple windows
- a final chronological holdout split

Defaults:

- `validation_fraction = 0.2`
- `min_validation_rows = 14`
- `min_training_rows = 30`
- `walk_forward_windows = 3`
- `seasonal_period = 7`

This means:

- each validation window uses only earlier rows as training data
- the latest holdout window is reported in `metrics.json`
- the job fails if there is not enough history

## 8. Model Hyperparameters

Default XGBoost settings:

- `xgb_n_estimators = 300`
- `xgb_max_depth = 6`
- `xgb_learning_rate = 0.05`
- `xgb_subsample = 0.9`
- `xgb_colsample_bytree = 0.9`
- `xgb_reg_lambda = 1.0`
- `random_state = 42`

You can override them:

```bash
python scripts/train_baseline_model.py \
  --features-path data/processed/features \
  --output-root artifacts/model \
  --target-column target_next_day_price_coriander \
  --walk-forward-windows 4 \
  --seasonal-period 7 \
  --xgb-n-estimators 400 \
  --xgb-max-depth 8 \
  --xgb-learning-rate 0.03
```

## 9. What the Training Code Does

The training flow in [phase_c_train_multi.py](D:/AIT/MLOps/project/repos/agri-price-mlops/ml/training/phase_c_train_multi.py) does this:

- loads the Phase B features Parquet dataset
- parses and sorts by `date`
- resolves the selected target columns, or all targets by default
- drops rows where any selected target is null
- checks that all remaining feature columns are numeric
- builds multiple walk-forward train/validation windows
- evaluates:
  - `xgboost`
  - `persistence`
  - `seasonal_naive`
- computes per-target and overall metrics
- computes:
  - `mae`
  - `rmse`
- writes:
  - final trained model artifact
  - holdout metrics
  - training summary
  - model comparison report

## 10. Validate the Outputs

After training, check:

```text
artifacts/model/model.pkl
artifacts/model/metrics.json
artifacts/model/training_summary.json
artifacts/model/comparison_report.json
```

Open `metrics.json` and confirm it includes:

- `mae`
- `rmse`
- `train_rows`
- `validation_rows`

Open `training_summary.json` and confirm it includes:

- `target_columns`
- `feature_columns`
- `holdout_train_date_range`
- `holdout_validation_date_range`
- `config`

Open `comparison_report.json` and confirm it includes:

- `models.xgboost`
- `models.persistence`
- `models.seasonal_naive`
- per-target metrics under `by_target`
- `winner`

## 11. Common Failure Cases

### Error: features dataset does not exist

Cause:

- wrong `--features-path`
- Phase B output was not generated yet

Fix:

- verify `data/processed/features` exists
- rerun Phase B if needed

### Error: target columns not found

Cause:

- wrong target name
- one or more requested target columns do not exist in the features dataset

Fix:

- inspect Phase B schema
- use target columns that actually exist in `features`

### Error: no rows with non-null target values

Cause:

- not enough history
- one or more selected target columns are empty for the selected range

Fix:

- ingest/backfill more raw data
- rerun Phase B

### Error: not enough rows for time-aware split

Cause:

- dataset is too small

Fix:

- collect more historical data
- or lower:
  - `--min-training-rows`
  - `--min-validation-rows`

### Error: non-numeric feature columns found

Cause:

- Phase B output schema is not purely numeric apart from `date`

Fix:

- inspect the features dataset
- remove or convert non-numeric columns before training

### Error: xgboost is required for Phase C

Cause:

- `xgboost` is not installed in the current environment

Fix:

- run:
  - `pip install -r ml/training/requirements.txt`

## 12. Recommended Workflow

Use this order:

1. finish Phase B and verify `features`
2. inspect `features/_meta/feature_schema.json`
3. choose all target columns or a subset
4. run Phase C locally
5. inspect `comparison_report.json`
6. inspect `metrics.json`
6. keep the artifact directory for Phase D inference

## 13. Example End-to-End Command

```bash
python scripts/train_baseline_model.py \
  --features-path data/processed/features \
  --output-root artifacts/model \
  --target-columns target_next_day_price_coriander,target_next_day_price_kale,target_next_day_price_lime,target_next_day_price_orange,target_next_day_price_red_chili \
  --validation-fraction 0.2 \
  --min-validation-rows 14 \
  --min-training-rows 30 \
  --walk-forward-windows 3 \
  --seasonal-period 7 \
  --xgb-n-estimators 300 \
  --xgb-max-depth 6 \
  --xgb-learning-rate 0.05 \
  --xgb-subsample 0.9 \
  --xgb-colsample-bytree 0.9 \
  --xgb-reg-lambda 1.0 \
  --random-state 42
```

## 14. Current Limitation

The current code trains locally and writes local artifacts.

It does not yet:

- train on SageMaker
- register a model
- upload artifacts to S3 automatically
- run model monitoring / retraining automation

Those can be added later after the baseline is validated.
