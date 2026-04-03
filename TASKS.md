# Project Task List (MVP for Term Project)

Derived from `docs/playbook.docx`, but reduced to a small, finishable scope for a few-day term project.

## Scope Rule

- [x] Keep only one environment: `dev`
- [ ] Keep only one working end-to-end pipeline
- [x] Use multi-product data in the ETL table
- [ ] Keep the first modeling target limited to one product column
- [x] Prefer simple working implementation over production-grade design

## Phase 0 - Foundation

- [x] Confirm AWS region and one `dev` environment
- [x] Define simple naming convention for bucket, Lambdas, Glue job, and model artifacts
- [x] Define minimal S3 layout:
  - [x] `raw/price/`
  - [x] `raw/weather/`
  - [x] `processed/features/`
  - [x] `artifacts/model/`
- [x] Decide the product set to include in the demo
- [x] Define the minimum schema needed for raw and processed data

## Phase A - Raw Ingestion

- [x] Create one raw S3 bucket
- [x] Finalize raw folder convention for price data
- [x] Finalize raw folder convention for weather data
- [x] Complete price ingestion Lambda
- [x] Complete weather ingestion Lambda
- [x] Ensure both Lambdas save raw API responses to S3
- [x] Add simple logs:
  - [x] request date
  - [x] status code
  - [x] S3 object key
- [x] Test price ingestion manually
- [x] Test weather ingestion manually
- [x] Verify raw files landed in S3
- [x] Add EventBridge schedule for daily runs

## Phase B - Prepare Dataset

- [x] Read raw price data
- [x] Read raw weather data
- [x] Clean and standardize key fields
- [x] Standardize date format
- [x] Join price and weather on date
- [x] Create one simple feature table
- [x] Save processed dataset to S3
- [x] Validate final columns and schema

## Phase C - Train Baseline Model

- [ ] Load processed dataset
- [ ] Split data with time-aware train/validation logic
- [ ] Train one baseline model
- [ ] Evaluate with one or two simple metrics
- [ ] Save trained model artifact
- [ ] Save evaluation result

## Phase D - Simple Prediction Demo

- [ ] Run prediction from the trained model
- [ ] Save prediction output to file or S3
- [ ] Show model version or artifact path in the output
- [ ] Prepare one demo flow that can be presented clearly

## Phase E - Minimal Documentation

- [ ] Write setup steps
- [ ] Write run steps for ingestion
- [ ] Write run steps for preprocessing
- [ ] Write run steps for training
- [ ] Write run steps for prediction/demo
- [ ] Write brief architecture summary

## Optional Only If Time Remains

- [ ] Replace preprocessing script with Glue job if not already done
- [ ] Package infrastructure with Terraform
- [ ] Add dead-letter queue for Lambda failures
- [ ] Add CloudWatch metrics
- [ ] Add simple retraining trigger
- [ ] Add separate `prod` config

## Demo Definition of Done

- [ ] Price data is ingested into S3 raw
- [ ] Weather data is ingested into S3 raw
- [ ] One processed dataset is produced
- [ ] One model is trained successfully
- [ ] One prediction output is generated
- [ ] The full MVP flow can be explained and demonstrated end-to-end
