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

## Phase C - Prototype Local Training

- [x] Load processed dataset
- [x] Split data with time-aware train/validation logic
- [x] Train one multi-output prototype model locally
- [x] Evaluate against baseline models
- [x] Save trained model artifact
- [x] Save evaluation result

## Phase D - Cloud ML Pipeline

- [ ] Convert Phase C training code into a SageMaker-compatible training step
- [ ] Create SageMaker evaluation step
- [ ] Create SageMaker registration step
- [ ] Define SageMaker `Train -> Evaluate -> Register` pipeline
- [ ] Create SageMaker model package group
- [ ] Run SageMaker pipeline manually once
- [ ] Confirm one registered model version exists in SageMaker

## Phase E - Inference and Deployment

- [ ] Run prediction from the registered model
- [ ] Save prediction output to file or S3
- [ ] Show model version or artifact path in the output
- [ ] Define endpoint deployment path
- [ ] Prepare one demo flow that can be presented clearly

## Phase F - Monitoring and Retraining

- [ ] Save prediction outputs for monitoring
- [ ] Build actual-vs-predicted comparison dataset
- [ ] Query actual-vs-predicted with Athena
- [ ] Publish monitoring metrics to CloudWatch
- [ ] Add EventBridge trigger for SageMaker Pipeline execution
- [ ] Add fully automated cloud retraining path

## Phase G - Documentation

- [ ] Write setup steps
- [ ] Write run steps for ingestion
- [ ] Write run steps for preprocessing
- [ ] Write run steps for SageMaker training pipeline
- [ ] Write run steps for prediction and deployment
- [ ] Write run steps for monitoring and retraining
- [ ] Write brief architecture summary

## Optional Only If Time Remains

- [ ] Package infrastructure with Terraform
- [ ] Add dead-letter queue for Lambda failures
- [ ] Add CloudWatch metrics dashboards
- [ ] Add separate `prod` config

## Demo Definition of Done

- [x] Price data is ingested into S3 raw
- [x] Weather data is ingested into S3 raw
- [x] One processed dataset is produced
- [x] One prototype model is trained successfully
- [ ] One SageMaker `Train -> Evaluate -> Register` pipeline runs successfully
- [ ] One registered model exists in SageMaker
- [ ] One prediction output is generated from the registered model
- [ ] Monitoring path for actual vs predicted is defined
- [ ] Automated cloud retraining path is defined
- [ ] The full proposal-aligned flow can be explained and demonstrated end-to-end
