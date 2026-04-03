# Project Task List (MVP for Term Project)

Derived from `docs/playbook.docx`, but reduced to a small, finishable scope for a few-day term project.

## Scope Rule

- [x] Keep only one environment: `dev`
- [ ] Keep only one working end-to-end pipeline
- [ ] Start with one vegetable / product only
- [ ] Start with one daily prediction target only
- [x] Prefer simple working implementation over production-grade design

## Phase 0 - Foundation

- [x] Confirm AWS region and one `dev` environment
- [ ] Define simple naming convention for bucket, Lambdas, Glue job, and model artifacts
- [ ] Define minimal S3 layout:
  - [x] `raw/price/`
  - [x] `raw/weather/`
  - [ ] `processed/features/`
  - [ ] `artifacts/model/`
- [ ] Decide the single product / target to use for the demo
- [ ] Define the minimum schema needed for raw and processed data

## Phase A - Raw Ingestion

- [x] Create one raw S3 bucket
- [x] Finalize raw folder convention for price data
- [x] Finalize raw folder convention for weather data
- [x] Complete price ingestion Lambda
- [x] Complete weather ingestion Lambda
- [x] Ensure both Lambdas save raw API responses to S3
- [ ] Add simple logs:
  - [ ] request date
  - [ ] status code
  - [ ] S3 object key
- [x] Test price ingestion manually
- [x] Test weather ingestion manually
- [x] Verify raw files landed in S3
- [x] Add EventBridge schedule for daily runs

## Phase B - Prepare Dataset

- [ ] Read raw price data
- [ ] Read raw weather data
- [ ] Clean and standardize key fields
- [ ] Standardize date format
- [ ] Join price and weather on date
- [ ] Create one simple feature table
- [ ] Save processed dataset to S3
- [ ] Validate final columns and schema

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
