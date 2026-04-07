# Project Task List

Derived from `docs/playbook.docx` and updated to reflect the current implementation state.

## Scope Rule

- [x] Keep only one environment: `dev`
- [ ] Keep only one working end-to-end pipeline
- [x] Use multi-product data in the ETL table
- [x] Train one multi-output model for multiple product targets
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
- [x] Add local historical backfill scripts for price and weather
- [x] Run historical backfill for the proposal training range

## Phase B - Prepare Dataset

- [x] Read raw price data
- [x] Read raw weather data
- [x] Clean and standardize key fields
- [x] Standardize date format
- [x] Join price and weather on date
- [x] Create one simple feature table
- [x] Save processed dataset to S3
- [x] Validate final columns and schema

## Phase C - Train Forecasting Model

- [x] Load processed dataset
- [x] Split data with time-aware train/validation logic
- [x] Train one multi-output model
- [x] Evaluate against baseline models
- [x] Save trained model artifact
- [x] Save evaluation result

## Phase D - Inference and Deployment

- [ ] Run prediction from the trained model
- [ ] Save prediction output to file or S3
- [ ] Show model version or artifact path in the output
- [ ] Package model artifact for SageMaker
- [ ] Upload model artifact to S3
- [ ] Register model in SageMaker Model Registry
- [ ] Define endpoint deployment path
- [ ] Prepare one demo flow that can be presented clearly

## Phase E - Monitoring and Retraining

- [ ] Save prediction outputs for monitoring
- [ ] Build actual-vs-predicted comparison dataset
- [ ] Query actual-vs-predicted with Athena
- [ ] Publish monitoring metrics to CloudWatch
- [ ] Add retraining trigger path

## Phase F - Documentation

- [ ] Write setup steps
- [ ] Write run steps for ingestion
- [ ] Write run steps for preprocessing
- [ ] Write run steps for training
- [ ] Write run steps for prediction/deployment
- [ ] Write run steps for monitoring/retraining
- [ ] Write brief architecture summary

## Optional Only If Time Remains

- [ ] Replace preprocessing script with Glue job if not already done
- [ ] Package infrastructure with Terraform
- [ ] Add dead-letter queue for Lambda failures
- [ ] Add CloudWatch metrics
- [ ] Add simple retraining trigger
- [ ] Add separate `prod` config

## Demo Definition of Done

- [x] Price data is ingested into S3 raw
- [x] Weather data is ingested into S3 raw
- [x] One processed dataset is produced
- [x] One model is trained successfully
- [ ] One prediction output is generated
- [ ] One registered model exists in SageMaker
- [ ] Monitoring path for actual vs predicted is defined
- [ ] The full MVP flow can be explained and demonstrated end-to-end
