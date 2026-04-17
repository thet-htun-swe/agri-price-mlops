# Agri Price MLOps System

End-to-end MLOps pipeline for daily agricultural price prediction with:

- automated ingestion
- feature transformation
- model training/evaluation/registration on SageMaker
- daily batch inference
- drift monitoring with Athena + CloudWatch
- optional human-in-the-loop approval before retraining

---

## 1) Final Architecture Overview

The implemented production flow is:

1. **Ingest raw data daily**
   - `lambda_ingest_prices`
   - `lambda_ingest_weather`
   - writes JSON to `s3://agri-price-dev-raw/`

2. **Transform raw -> processed features**
   - Glue built-in schedule runs Glue job `agri-price-dev-phase-b` directly
   - Glue script: `glue/jobs/build_daily_features_job.py`
   - writes:
     - `processed/features/` (training + actuals source)
     - `inference/input/run_date=YYYY-MM-DD/...` (daily inference payload)

3. **Train / Evaluate / Register model (SageMaker Pipeline)**
   - Pipeline: `agri-price-train-evaluate-register`
   - training entry point: `sagemaker/pipeline/train.py`
   - evaluation script: `sagemaker/pipeline/evaluate.py`
   - inference entry point for model package: `sagemaker/pipeline/inference.py`
   - model registry group: `agri-price-multi-output`

4. **Daily inference**
   - `agri-daily-inference` Lambda selects latest Approved model package
   - starts SageMaker Batch Transform
   - writes raw output:
     - `predictions/raw/run_date=YYYY-MM-DD/`

5. **Curate predictions**
   - `agri-curate-predictions` Lambda converts raw transform output to curated dataset
   - writes:
     - partitioned parquet for analytics:
       - `predictions/curated/run_date=YYYY-MM-DD/predictions.parquet`
     - latest snapshot for frontend:
       - `predictions/curated/latest/predictions.json`

6. **Monitor drift**
   - `agri-metrics-publisher` Lambda:
     - runs Athena partition refresh (`MSCK REPAIR`)
     - computes MAPE from `agri_actual_vs_pred`
     - publishes `OverallMAPE` metric to CloudWatch namespace `AgriPriceML`
   - CloudWatch alarm `agri-overall-mape-alarm` evaluates threshold

7. **Retraining trigger**
   - Alarm -> EventBridge rule -> Step Functions human-approval flow
   - Retraining starts only after explicit approval

8. **Frontend**
   - static site reads:
     - `predictions/curated/latest/predictions.json`

---

## 2) Repository Areas

- `services/`
  - Lambda function source code (ingestion, inference, curation, monitor, retraining, approval flow)
- `glue/jobs/`
  - Glue ETL/transformation scripts
- `sagemaker/pipeline/`
  - SageMaker pipeline scripts and definition builder
- `notebooks/`
  - manual setup/operations notebooks
- `sql/athena/actual_vs_pred/`
  - Athena DDL and view SQL for monitoring
- `docs/`
  - runbooks, setup instructions, architecture references
- `web/static-site/`
  - static frontend assets

---

## 3) What Is Runtime-Critical vs Setup-Only

### Runtime-critical (used by automation)

- `glue/jobs/build_daily_features_job.py`
- `sagemaker/pipeline/train.py`
- `sagemaker/pipeline/evaluate.py`
- `sagemaker/pipeline/inference.py`
- `services/**/handler.py` (active Lambda handlers)

### Setup/update only (manual operations)

- `notebooks/sagemaker_pipeline_studio_setup.ipynb`
- `sagemaker/pipeline/pipeline_definition.py`

### Archived/legacy

- `notebooks/archive/`
- `sagemaker/archive/local-artifacts/`

---

## 4) Zero-to-Run (High Level)

1. Create S3 bucket and prefixes (`agri-price-dev-raw`).
2. Deploy/prepare Lambdas in `services/` with env vars.
3. Create Glue job with `glue/jobs/build_daily_features_job.py` and configure Glue built-in schedule.
4. Run `notebooks/sagemaker_pipeline_studio_setup.ipynb` once to create/update SageMaker pipeline and code artifacts in S3.
5. Approve at least one model package in model registry.
6. Create Athena DB/tables/views using `sql/athena/actual_vs_pred/*.sql`.
7. Create CloudWatch metric alarm for `AgriPriceML / OverallMAPE`.
8. Create EventBridge schedules and alarm-trigger rules.
9. (Optional) Configure Step Functions + SNS + API Gateway for human approval.

---

## 5) Monitoring Metric Logic

Current monitor Lambda computes per-target MAPE and publishes average:

- metric name: `OverallMAPE`
- namespace: `AgriPriceML`
- dimension: `ModelPackageGroup=agri-price-multi-output`

Important notes:

- MAPE becomes empty when actual values are null/zero for selected run date.
- Monitor Lambda now repairs Athena partitions before metric query.

---

## 6) Daily Schedule Guidance

Set schedules after source data availability window (provider updates after local evening).

- Use UTC cron in EventBridge/Glue.
- Keep ingestion first, then transform, then inference, then curation, then monitoring with gaps between each stage.

---

## 7) Human-in-the-Loop Mode (Final Architecture)

Final production flow uses human approval before retraining:

- Drift alarm triggers EventBridge
- EventBridge starts Step Functions approval workflow
- Step Functions calls `agri-send-approval-request` Lambda
- `agri-send-approval-request` publishes to SNS topic (approval email sent)
- Approver calls API Gateway decision endpoint
- API Gateway invokes `agri-approval-decision` Lambda
- `agri-approval-decision` resumes Step Functions with Approve/Reject decision
- Approved -> starts retraining pipeline
- Rejected -> retraining skipped

See runbook:

- `docs/human_in_loop_retraining_runbook.md`

---

## 8) Drift Injection Experiment

To validate monitoring/retraining chain safely (without overwriting production parquet), use:

- `docs/drift_injection_experiment_runbook.md`

This uses Athena injected test views and rollback steps.

---

## 9) Architecture Diagram

Mermaid diagram file:

- `docs/final_system_architecture.md`
