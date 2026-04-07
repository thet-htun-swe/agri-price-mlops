# Proposal Alignment Fix Plan

This document lists the gaps between the current implementation and the original proposal in [proposal.docx](D:/AIT/MLOps/project/repos/agri-price-mlops/docs/proposal.docx), then prioritizes the fixes.

## Must Fix Now

### 1. Historical Backfill

Why:

- the proposal dataset is daily price and weather history over `2022–2025`
- the current pipeline mainly proves daily ingestion and Phase B logic
- without historical backfill, Phase C is not proposal-valid

What to do:

- add a backfill mode for price ingestion
- add a backfill mode for weather ingestion
- write raw history into the same raw S3 layout
- rerun Phase B on the full historical range
- verify the `features` table has enough non-null target rows for all five products

Deliverable:

- reproducible raw S3 history covering the proposal experiment range

### 2. Phase C Primary Model Must Be XGBoost

Why:

- the proposal positions XGBoost as the main model
- current [phase_c_train.py](D:/AIT/MLOps/project/repos/agri-price-mlops/ml/training/phase_c_train.py) uses Random Forest only

What to do:

- replace Random Forest as the main trainer with XGBoost
- keep Random Forest only as an optional baseline if needed
- save:
  - model artifact
  - feature list
  - metrics report

Deliverable:

- local XGBoost training script that runs from `features`

### 3. Add Baseline Comparisons

Why:

- the proposal expects baseline comparison, not just one model score
- the playbook explicitly says to compare before cloud deployment

Minimum baselines:

- persistence
- seasonal naive

Optional:

- ARIMA if time permits

Deliverable:

- one evaluation output comparing XGBoost vs baselines on the same split

### 4. Add Walk-Forward or Rolling-Origin Validation

Why:

- the proposal explicitly references walk-forward validation
- the current split is only one chronological holdout

What to do:

- add rolling evaluation windows
- report averaged metrics across folds/windows
- keep a simple single holdout too if useful for debugging

Deliverable:

- evaluation method aligned with time-series forecasting practice in the proposal

## Should Fix Soon

### 5. Add Explicit Outlier Handling in Phase B

Why:

- the proposal says preprocessing handles missing values and removes anomalous outliers
- current Phase B does not do outlier treatment

Minimum acceptable fix:

- document a simple outlier policy
- either winsorize/cap or flag extreme values
- do not silently drop too much data

Deliverable:

- consistent outlier rule in Phase B docs and code

### 6. Tighten Processed Dataset Versioning

Why:

- proposal and playbook lean toward a governed processed zone
- current output path is workable but loose

What to do:

- move toward paths like:
  - `processed/dataset=clean_prices/version=v1/`
  - `processed/dataset=clean_weather/version=v1/`
  - `processed/dataset=features/version=v1/`

Deliverable:

- stable versioned processed contract for SageMaker and monitoring

## Can Defer Until After Local Model Is Credible

### 7. SageMaker Training Job

### 8. Model Registry

### 9. Endpoint Deployment

### 10. Prediction Logging

### 11. Athena Join for Actual vs Prediction

### 12. CloudWatch Monitoring Lambda

### 13. EventBridge Retraining Trigger

## Recommended Execution Order

1. backfill raw history
2. rebuild Phase B features on full history
3. upgrade Phase C to XGBoost
4. add persistence and seasonal naive baselines
5. add walk-forward validation
6. add outlier policy
7. tighten dataset versioning
8. then move to SageMaker and monitoring loop

## Immediate Next Step

The correct next task is historical backfill, not SageMaker.

Once backfill is complete:

- rerun Phase B
- validate the rebuilt features dataset
- then begin the XGBoost Phase C upgrade
