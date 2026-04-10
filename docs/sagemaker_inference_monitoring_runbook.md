# SageMaker Inference and Monitoring Runbook

This runbook completes the next proposal-aligned steps after `Train -> Evaluate -> Register`.

Scope:
- inference from registered model
- prediction outputs to S3
- Athena actual-vs-predicted comparison
- CloudWatch monitoring
- EventBridge-triggered retraining

Keep it simple: run batch inference once per day and trigger retraining only when MAPE breaches threshold.

## 1. Prerequisites

- SageMaker pipeline already succeeds end-to-end.
- Model package exists in group `agri-price-multi-output`.
- Processed features exist at `s3://agri-price-dev-raw/processed/features/`.
- One IAM role can access SageMaker, S3, Athena, CloudWatch, EventBridge.

## 2. Batch Inference to S3

Create a new Studio notebook and run:

```python
import boto3, json
from datetime import datetime, timezone

region = "us-east-1"
bucket = "agri-price-dev-raw"
role_arn = "arn:aws:iam::654654220088:role/LabRole"
model_package_group = "agri-price-multi-output"

run_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
input_s3 = f"s3://{bucket}/processed/features/"
output_s3 = f"s3://{bucket}/predictions/raw/run_date={run_date}/"

sm = boto3.client("sagemaker", region_name=region)
```

Find latest approved model package:

```python
resp = sm.list_model_packages(
    ModelPackageGroupName=model_package_group,
    ModelApprovalStatus="Approved",
    SortBy="CreationTime",
    SortOrder="Descending",
    MaxResults=1,
)
model_package_arn = resp["ModelPackageSummaryList"][0]["ModelPackageArn"]
model_package_arn
```

Create model and run batch transform:

```python
model_name = f"agri-price-batch-model-{run_date.replace('-', '')}"
transform_job_name = f"agri-price-batch-predict-{run_date.replace('-', '')}"

sm.create_model(
    ModelName=model_name,
    ExecutionRoleArn=role_arn,
    Containers=[{"ModelPackageName": model_package_arn}],
)

sm.create_transform_job(
    TransformJobName=transform_job_name,
    ModelName=model_name,
    TransformInput={
        "DataSource": {"S3DataSource": {"S3DataType": "S3Prefix", "S3Uri": input_s3}},
        "ContentType": "application/x-parquet",
        "SplitType": "None",
    },
    TransformOutput={
        "S3OutputPath": output_s3,
        "Accept": "application/json",
        "AssembleWith": "Line",
    },
    TransformResources={"InstanceType": "ml.m5.large", "InstanceCount": 1},
)

print(transform_job_name)
```

Wait until the transform job is `Completed` before moving on.

## 3. Curate Prediction Output

Create a small Lambda or notebook job to normalize raw output into a curated prefix:

- input: `s3://agri-price-dev-raw/predictions/raw/run_date=YYYY-MM-DD/`
- output: `s3://agri-price-dev-raw/predictions/curated/run_date=YYYY-MM-DD/`

Curated columns:
- `date`
- `target_next_day_price_coriander_pred`
- `target_next_day_price_kale_pred`
- `target_next_day_price_lime_pred`
- `target_next_day_price_orange_pred`
- `target_next_day_price_red_chili_pred`
- `model_package_arn`
- `run_date`

Use Parquet for Athena performance.

## 4. Athena: Actual vs Predicted

Create external tables:

- `agri_features_actual` over `s3://agri-price-dev-raw/processed/features/`
- `agri_predictions_curated` over `s3://agri-price-dev-raw/predictions/curated/`

Create a view:

```sql
CREATE OR REPLACE VIEW agri_actual_vs_pred AS
SELECT
  a.date,
  a.target_next_day_price_coriander AS actual_coriander,
  p.target_next_day_price_coriander_pred AS pred_coriander,
  a.target_next_day_price_kale AS actual_kale,
  p.target_next_day_price_kale_pred AS pred_kale,
  a.target_next_day_price_lime AS actual_lime,
  p.target_next_day_price_lime_pred AS pred_lime,
  a.target_next_day_price_orange AS actual_orange,
  p.target_next_day_price_orange_pred AS pred_orange,
  a.target_next_day_price_red_chili AS actual_red_chili,
  p.target_next_day_price_red_chili_pred AS pred_red_chili,
  p.run_date
FROM agri_features_actual a
JOIN agri_predictions_curated p
  ON a.date = p.date;
```

Compute daily model metric summary (example MAPE):

```sql
SELECT
  run_date,
  AVG(ABS((actual_coriander - pred_coriander) / NULLIF(actual_coriander, 0))) * 100 AS mape_coriander,
  AVG(ABS((actual_kale - pred_kale) / NULLIF(actual_kale, 0))) * 100 AS mape_kale,
  AVG(ABS((actual_lime - pred_lime) / NULLIF(actual_lime, 0))) * 100 AS mape_lime,
  AVG(ABS((actual_orange - pred_orange) / NULLIF(actual_orange, 0))) * 100 AS mape_orange,
  AVG(ABS((actual_red_chili - pred_red_chili) / NULLIF(actual_red_chili, 0))) * 100 AS mape_red_chili
FROM agri_actual_vs_pred
GROUP BY run_date
ORDER BY run_date DESC;
```

## 5. CloudWatch Monitoring

Create Lambda `agri-metrics-publisher`:

- run Athena metric query
- compute one overall KPI (example mean MAPE across targets)
- publish custom metric:
  - namespace: `AgriPriceML`
  - metric name: `OverallMAPE`
  - dimensions: `ModelPackageGroup=agri-price-multi-output`

Create CloudWatch alarm:

- metric: `AgriPriceML/OverallMAPE`
- threshold: `12`
- periods: `2` consecutive datapoints
- comparison: `GreaterThanThreshold`

## 6. EventBridge Retraining Trigger

Create EventBridge rule:

- source alarm state change from CloudWatch
- condition: state `ALARM` for `OverallMAPE` alarm
- target: Lambda `agri-start-retraining`

Lambda `agri-start-retraining` calls:

```python
import boto3

sm = boto3.client("sagemaker", region_name="us-east-1")

sm.start_pipeline_execution(
    PipelineName="agri-price-train-evaluate-register",
    PipelineParameters=[
        {
            "Name": "TargetColumns",
            "Value": "target_next_day_price_coriander,target_next_day_price_kale,target_next_day_price_lime,target_next_day_price_orange,target_next_day_price_red_chili",
        },
        {"Name": "FeaturesS3Uri", "Value": "s3://agri-price-dev-raw/processed/features/"},
    ],
)
```

## 7. Definition of Done

- one batch inference job completed and wrote predictions to S3
- Athena query returns actual-vs-predicted metrics
- CloudWatch custom metric is visible
- alarm transitions to `ALARM` in a test
- EventBridge target starts a new pipeline execution
