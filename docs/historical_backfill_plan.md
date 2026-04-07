# Historical Backfill Plan

This document records the agreed approach for preparing the first training dataset while keeping the current Lambda ingestion design focused on scheduled incremental updates.

## Decision

Historical data backfill will be done locally first.

The existing Lambda ingestion handlers will remain responsible for scheduled raw ingestion only:

- daily or weekly incremental price ingestion
- daily or weekly incremental weather ingestion
- EventBridge-triggered execution

This means Lambda does **not** need to handle the initial multi-year historical backfill.

## Why This Is Acceptable

This approach still satisfies the proposal at the current stage because:

- the proposal requires historical data for model training
- it does not require Lambda to perform the initial historical backfill
- the playbook explicitly recommends local model development before cloud deployment
- the current Lambdas already define the correct raw data contract and S3 layout for future scheduled ingestion

## Role of Each Component

### Lambda

Lambda is responsible for:

- ongoing raw ingestion after the initial dataset is built
- scheduled collection through EventBridge
- appending new raw data to the raw S3 zone

Lambda is **not** responsible for:

- initial 4-year historical collection
- long-running bulk backfill jobs

### Local Historical Backfill

Local backfill is responsible for:

- collecting historical price data
- collecting historical weather data
- building the first large raw dataset for model development

This historical data should still follow the same logical schema as current raw ingestion so that Phase B can process it consistently.

### Glue Phase B

Glue remains responsible for:

- cleaning
- translation
- reshaping
- feature engineering
- writing the processed feature dataset

### Phase C Local Training

Local training remains responsible for:

- validating the first working model cheaply
- experimenting with baselines and XGBoost
- confirming that the feature dataset is usable before SageMaker work

### SageMaker Later

SageMaker remains a later phase for:

- cloud training jobs
- model artifact storage
- model registry
- deployment

## Required Historical Dataset Scope

To align with the proposal, prepare historical data for:

- date range: `2022-01-01` to `2025-12-31`
- products:
  - `P13087`
  - `P13083`
  - `P13043`
  - `P13002`
  - `P14001`
- weather variables:
  - `temperature_2m_mean`
  - `precipitation_sum`
  - `relative_humidity_2m_mean`

## Task List

### Backfill Preparation

- [x] Confirm the exact five proposal products and their product IDs
- [x] Define the historical date range for local collection
- [x] Decide the local collection method for price data
- [x] Decide the local collection method for weather data
- [x] Preserve the raw schema structure expected by Phase B

### Historical Raw Collection

- [x] Add local backfill scripts for price and weather
- [x] Add manual backfill templates for all months and selected products
- [x] Collect historical raw price data for all target products
- [x] Collect historical raw weather data for the same date range
- [x] Store the historical raw data in a format Phase B can consume
- [x] Verify date coverage across the full period
- [x] Verify product coverage across all selected products

### Feature Dataset Build

- [x] Run Phase B on the historical raw data
- [x] Validate `clean_prices`
- [x] Validate `clean_weather`
- [x] Validate `features`
- [x] Confirm one row per day in the final features dataset
- [x] Confirm target columns exist and have enough non-null rows

### Training Readiness

- [x] Confirm the chosen target column has enough rows for training
- [x] Confirm the feature schema is stable
- [x] Confirm the dataset is large enough for chronological train/validation/test work

### Ongoing Incremental Pipeline

- [x] Keep Lambda price ingestion scheduled by EventBridge
- [x] Keep Lambda weather ingestion scheduled by EventBridge
- [ ] Ensure new raw data continues landing in S3 after the initial backfill
- [ ] Plan periodic Phase B reruns as new raw data arrives

## Current Status

Completed:

- local backfill approach chosen
- raw schema preserved through shared ingestion helpers
- local backfill scripts implemented
- manual monthly template scaffold generated
- historical Phase B rebuild run successfully
- Phase C upgraded in parallel while raw collection continues

Still in progress:

- finish filling the historical raw price files
- finish filling the historical raw weather files
- validate the rebuilt processed datasets and confirm training readiness

## Implemented Backfill Entry Points

The repo now includes local backfill scripts that preserve the Lambda-compatible raw schema and directory structure:

- [backfill_prices.py](D:/AIT/MLOps/project/repos/agri-price-mlops/scripts/backfill_prices.py)
- [backfill_weather.py](D:/AIT/MLOps/project/repos/agri-price-mlops/scripts/backfill_weather.py)
- [backfill_common.py](D:/AIT/MLOps/project/repos/agri-price-mlops/scripts/backfill_common.py)

These scripts:

- split requests into monthly windows
- write raw JSON files under the same logical layout as Lambda ingestion
- keep the request metadata that Phase B already expects

The repo also includes shared raw contract helpers used by both Lambda ingestion and local backfill:

- [price_contract.py](D:/AIT/MLOps/project/repos/agri-price-mlops/services/ingestion_common/price_contract.py)
- [weather_contract.py](D:/AIT/MLOps/project/repos/agri-price-mlops/services/ingestion_common/weather_contract.py)

And a manual scaffold for paste-in historical responses:

- [manual_backfill_scaffold.md](D:/AIT/MLOps/project/repos/agri-price-mlops/docs/manual_backfill_scaffold.md)
- [manual_backfill_templates](D:/AIT/MLOps/project/repos/agri-price-mlops/manual_backfill_templates)

## Example Commands

### Price history

```powershell
python scripts\backfill_prices.py `
  --product-ids P13087,P13083,P13043,P13002,P14001 `
  --start-date 2022-01-01 `
  --end-date 2025-12-31 `
  --output-root data\raw\price
```

### Weather history

```powershell
python scripts\backfill_weather.py `
  --start-date 2022-01-01 `
  --end-date 2025-12-31 `
  --output-root data\raw\weather `
  --latitude 13.7563 `
  --longitude 100.5018 `
  --timezone Asia/Bangkok
```

## Notes

- The scripts currently target local raw storage because the agreed approach is local historical collection first.
- Ongoing scheduled ingestion still belongs to the Lambda + EventBridge path.
- After backfill completes, run [build_daily_features.py](D:/AIT/MLOps/project/repos/agri-price-mlops/scripts/build_daily_features.py) to rebuild the historical `features` dataset.
- If the price API is unstable, use the manual scaffold under [manual_backfill_templates](D:/AIT/MLOps/project/repos/agri-price-mlops/manual_backfill_templates) and paste API responses into the wrapper files.

## Next Validation Step

After the raw backfill is complete, inspect:

- [validation_report.json](D:/AIT/MLOps/project/repos/agri-price-mlops/data/processed/features/_meta/validation_report.json)
- [feature_schema.json](D:/AIT/MLOps/project/repos/agri-price-mlops/data/processed/features/_meta/feature_schema.json)

Then confirm:

- duplicate dates are `0`
- the processed date range covers the intended historical period
- the target columns exist
- the selected target has enough non-null rows for Phase C
