# Lab Guide: Implement Inference + Monitoring + Retraining

This file is the step-by-step implementation guide for your final design:

- SageMaker pipeline trains/evaluates/registers model
- daily inference writes predictions to S3
- frontend reads predictions from S3
- Athena + monitor Lambda compute drift metrics
- CloudWatch alarm triggers retraining pipeline

## A) SageMaker Actions You Must Do First

These are the required SageMaker-side steps before EventBridge/Lambda automation.

### A.1 Confirm Training Pipeline Exists and Succeeds

Page:

- `SageMaker AI` -> left menu `Pipelines` -> `Pipelines`

Steps:

1. Click pipeline `agri-price-train-evaluate-register`.
2. Click `Executions` tab.
3. Confirm latest execution row is `Succeeded`.
4. Click that execution row to open its details/graph.
5. Confirm step statuses:
   - `TrainMultiOutputModel = Succeeded`
   - `EvaluateMultiOutputModel = Succeeded`
   - `RegisterMultiOutputModel = Succeeded`

Note:

- SageMaker Pipelines shows one execution per run.
- Train/Evaluate/Register are steps inside that execution, not separate top-level executions.

### A.2 Approve a Model Package in SageMaker Model Registry

Current Studio UI path (recommended):

- `SageMaker Studio` -> `Registry` -> `Registered Models`
- open `Agri Price Multi Output`
- open latest `Version`

Steps:

1. Open `Registered Models` and select `Agri Price Multi Output`.
2. Open latest model `Version`.
3. In version overview, check `Deploy` status card.
4. If not approved, change `Deploy` state to `Approved` (or use actions menu).
5. Save/confirm change.

Alternative (SDK) if UI control is restricted:

```python
import boto3
sm = boto3.client("sagemaker", region_name="us-east-1")
sm.update_model_package(
    ModelPackageArn="<model_package_arn>",
    ModelApprovalStatus="Approved"
)
```

Why:

- `agri-daily-inference` selects latest `Approved` package only.

### A.3 Verify Batch Transform Jobs Page

Page:

- `SageMaker AI` -> `Inference` -> `Batch transform jobs`

Use this page after daily inference Lambda runs to confirm:

- Job status `Completed`
- Input and output S3 paths are correct

### A.4 Optional: Test Daily Inference from SageMaker Studio Once

Page:

- `SageMaker Studio` -> open notebook `notebooks/sagemaker_inference_batch.ipynb`

Use this only for initial validation/debug.
Production recurring runs should be EventBridge + Lambda, not manual notebook runs.

## 1) AWS Pages You Will Use

- SageMaker AI Console
- S3 Console
- Athena Query Editor
- Lambda Console
- EventBridge Console
- CloudWatch Console
- IAM Console

## 2) Prepare S3 Paths

Use these paths consistently:

- features: `s3://agri-price-dev-raw/processed/features/`
- inference input payload: `s3://agri-price-dev-raw/inference/input/run_date=YYYY-MM-DD/payload/`
- inference raw output: `s3://agri-price-dev-raw/predictions/raw/run_date=YYYY-MM-DD/`
- inference curated output: `s3://agri-price-dev-raw/predictions/curated/run_date=YYYY-MM-DD/`
- Athena query output: `s3://agri-price-dev-raw/athena-results/`

## 3) Create Athena Objects

Page:

- `Athena` -> `Query editor`

Run SQL files in this order:

1. `sql/athena/actual_vs_pred/01_create_database_agri_mlops.sql`
2. `sql/athena/actual_vs_pred/02_create_table_agri_features_actual.sql`
3. `sql/athena/actual_vs_pred/03_create_table_agri_predictions_curated.sql`
4. `sql/athena/actual_vs_pred/04_msck_repair_agri_features_actual.sql`
5. `sql/athena/actual_vs_pred/05_create_view_agri_actual_vs_pred.sql`
6. `sql/athena/actual_vs_pred/07_msck_repair_agri_predictions_curated.sql`

## 4) Create Lambda: `agri-daily-inference`

Page:

- `Lambda` -> `Create function` -> `Author from scratch`

Fields:

- Function name: `agri-daily-inference`
- Runtime: `Python 3.12`
- Execution role: create/use role with SageMaker + S3 permissions

Open `Code` tab and paste:

```python
import os
import boto3
from datetime import datetime, timezone

REGION = os.environ.get("AWS_REGION", "us-east-1")
sm = boto3.client("sagemaker", region_name=REGION)

MODEL_PACKAGE_GROUP = os.environ["MODEL_PACKAGE_GROUP"]
SAGEMAKER_EXEC_ROLE_ARN = os.environ["SAGEMAKER_EXEC_ROLE_ARN"]

INPUT_S3_URI_TEMPLATE = os.environ["INPUT_S3_URI_TEMPLATE"]
OUTPUT_S3_URI_TEMPLATE = os.environ["OUTPUT_S3_URI_TEMPLATE"]

INSTANCE_TYPE = os.environ.get("INSTANCE_TYPE", "ml.m5.large")
INSTANCE_COUNT = int(os.environ.get("INSTANCE_COUNT", "1"))

def _latest_approved_model_package_arn():
    resp = sm.list_model_packages(
        ModelPackageGroupName=MODEL_PACKAGE_GROUP,
        ModelApprovalStatus="Approved",
        SortBy="CreationTime",
        SortOrder="Descending",
        MaxResults=1,
    )
    items = resp.get("ModelPackageSummaryList", [])
    if not items:
        raise RuntimeError(f"No Approved model package found in {MODEL_PACKAGE_GROUP}")
    return items[0]["ModelPackageArn"]

def _model_name_from_pkg_arn(pkg_arn: str) -> str:
    version = pkg_arn.rstrip("/").split("/")[-1]
    return f"agri-price-infer-v{version}"

def _ensure_model_exists(model_name: str, model_package_arn: str):
    try:
        sm.describe_model(ModelName=model_name)
    except sm.exceptions.ClientError as e:
        msg = str(e)
        if "Could not find model" in msg or "ValidationException" in msg:
            sm.create_model(
                ModelName=model_name,
                ExecutionRoleArn=SAGEMAKER_EXEC_ROLE_ARN,
                Containers=[{"ModelPackageName": model_package_arn}],
            )
        else:
            raise

def lambda_handler(event, context):
    run_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    run_stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")

    model_package_arn = _latest_approved_model_package_arn()
    model_name = _model_name_from_pkg_arn(model_package_arn)
    _ensure_model_exists(model_name, model_package_arn)

    input_s3 = INPUT_S3_URI_TEMPLATE.format(run_date=run_date)
    output_s3 = OUTPUT_S3_URI_TEMPLATE.format(run_date=run_date)

    transform_job_name = f"agri-price-batch-predict-{run_stamp}"

    sm.create_transform_job(
        TransformJobName=transform_job_name,
        ModelName=model_name,
        TransformInput={
            "DataSource": {"S3DataSource": {"S3DataType": "S3Prefix", "S3Uri": input_s3}},
            "ContentType": "application/json",
            "SplitType": "Line",
        },
        TransformOutput={
            "S3OutputPath": output_s3,
            "Accept": "application/json",
            "AssembleWith": "Line",
        },
        TransformResources={"InstanceType": INSTANCE_TYPE, "InstanceCount": INSTANCE_COUNT},
        BatchStrategy="SingleRecord",
        MaxPayloadInMB=1,
    )

    return {
        "status": "started",
        "run_date": run_date,
        "model_package_arn": model_package_arn,
        "model_name": model_name,
        "transform_job_name": transform_job_name,
        "input_s3": input_s3,
        "output_s3": output_s3,
    }
```

Click:

- `Deploy`

Then set Environment Variables:

- `MODEL_PACKAGE_GROUP=agri-price-multi-output`
- `SAGEMAKER_EXEC_ROLE_ARN=arn:aws:iam::654654220088:role/LabRole`
- `INPUT_S3_URI_TEMPLATE=s3://agri-price-dev-raw/inference/input/run_date={run_date}/payload/`
- `OUTPUT_S3_URI_TEMPLATE=s3://agri-price-dev-raw/predictions/raw/run_date={run_date}/`
- `INSTANCE_TYPE=ml.m5.large`
- `INSTANCE_COUNT=1`

## 5) Create Lambda: `agri-curate-predictions`

Page:

- `Lambda` -> `Create function` -> `Author from scratch`

Fields:

- Function name: `agri-curate-predictions`
- Runtime: `Python 3.12`

Code:

```python
import os
import json
import boto3
import pandas as pd
from io import BytesIO
from datetime import datetime, timezone

REGION = os.environ.get("AWS_REGION", "us-east-1")
s3 = boto3.client("s3", region_name=REGION)

BUCKET = os.environ["BUCKET"]
RAW_BASE = os.environ.get("RAW_BASE", "predictions/raw/")
CURATED_BASE = os.environ.get("CURATED_BASE", "predictions/curated/")
META_BASE = os.environ.get("META_BASE", "inference/input/")
MODEL_PACKAGE_GROUP = os.environ.get("MODEL_PACKAGE_GROUP", "agri-price-multi-output")

def _list_keys(prefix):
    resp = s3.list_objects_v2(Bucket=BUCKET, Prefix=prefix)
    return [x["Key"] for x in resp.get("Contents", [])]

def lambda_handler(event, context):
    run_date = event.get("run_date") if isinstance(event, dict) else None
    if not run_date:
        run_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    raw_prefix = f"{RAW_BASE}run_date={run_date}/"
    meta_prefix = f"{META_BASE}run_date={run_date}/meta/"
    curated_prefix = f"{CURATED_BASE}run_date={run_date}/"

    raw_keys = [k for k in _list_keys(raw_prefix) if k.endswith(".out")]
    if not raw_keys:
        raise RuntimeError(f"No .out files found in s3://{BUCKET}/{raw_prefix}")

    manifest_key = f"{meta_prefix}input_manifest.parquet"
    manifest_obj = s3.get_object(Bucket=BUCKET, Key=manifest_key)
    manifest = pd.read_parquet(BytesIO(manifest_obj["Body"].read()))

    pred_rows = []
    for k in raw_keys:
        text = s3.get_object(Bucket=BUCKET, Key=k)["Body"].read().decode("utf-8")
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            payload = json.loads(line)
            pred_rows.extend(payload.get("predictions", []))

    pred_df = pd.DataFrame(pred_rows).reset_index(drop=True)
    if len(pred_df) != len(manifest):
        raise RuntimeError(f"Prediction rows {len(pred_df)} != manifest rows {len(manifest)}")

    curated = pd.DataFrame({
        "date": manifest["date"],
        "target_next_day_price_coriander_pred": pred_df["target_next_day_price_coriander"],
        "target_next_day_price_kale_pred": pred_df["target_next_day_price_kale"],
        "target_next_day_price_lime_pred": pred_df["target_next_day_price_lime"],
        "target_next_day_price_orange_pred": pred_df["target_next_day_price_orange"],
        "target_next_day_price_red_chili_pred": pred_df["target_next_day_price_red_chili"],
        "model_package_group": MODEL_PACKAGE_GROUP,
        "run_date": run_date,
    })

    buf = BytesIO()
    curated.to_parquet(buf, index=False)
    out_key = f"{curated_prefix}predictions.parquet"
    s3.put_object(Bucket=BUCKET, Key=out_key, Body=buf.getvalue())

    return {"status": "ok", "run_date": run_date, "output": f"s3://{BUCKET}/{out_key}"}
```

Environment Variables:

- `BUCKET=agri-price-dev-raw`
- `RAW_BASE=predictions/raw/`
- `CURATED_BASE=predictions/curated/`
- `META_BASE=inference/input/`
- `MODEL_PACKAGE_GROUP=agri-price-multi-output`

## 6) Deploy Existing Monitor Lambda

Function:

- `agri-metrics-publisher`

Code source:

- `services/lambda_model_monitor/handler.py`

Environment Variables:

- `ATHENA_DATABASE=agri_mlops`
- `ATHENA_OUTPUT_S3=s3://agri-price-dev-raw/athena-results/`
- `CLOUDWATCH_NAMESPACE=AgriPriceML`
- `MODEL_PACKAGE_GROUP=agri-price-multi-output`
- `ATHENA_WORKGROUP=primary`

## 7) Create Lambda: `agri-start-retraining` (Optional but recommended)

Page:

- `Lambda` -> `Create function`

Code:

```python
import os
import boto3

REGION = os.environ.get("AWS_REGION", "us-east-1")
sm = boto3.client("sagemaker", region_name=REGION)

PIPELINE_NAME = os.environ["PIPELINE_NAME"]
TARGET_COLUMNS = os.environ["TARGET_COLUMNS"]
FEATURES_S3_URI = os.environ["FEATURES_S3_URI"]

def lambda_handler(event, context):
    resp = sm.start_pipeline_execution(
        PipelineName=PIPELINE_NAME,
        PipelineParameters=[
            {"Name": "TargetColumns", "Value": TARGET_COLUMNS},
            {"Name": "FeaturesS3Uri", "Value": FEATURES_S3_URI},
        ],
    )
    return {"status": "started", "pipeline_execution_arn": resp["PipelineExecutionArn"]}
```

Environment Variables:

- `PIPELINE_NAME=agri-price-train-evaluate-register`
- `TARGET_COLUMNS=target_next_day_price_coriander,target_next_day_price_kale,target_next_day_price_lime,target_next_day_price_orange,target_next_day_price_red_chili`
- `FEATURES_S3_URI=s3://agri-price-dev-raw/processed/features/`

## 8) EventBridge Rules

### Rule A/B/C: Daily cron rules (use EventBridge Scheduler)

Important:
- In current AWS UI, cron rules are created under `Scheduler`, not standard `Rules`.

Page:
- `EventBridge` -> left menu `Scheduler` -> `Schedules` -> `Create schedule`

Create 3 schedules:

1. `agri-daily-inference-schedule` -> target `agri-daily-inference`
2. `agri-daily-curate-schedule` -> target `agri-curate-predictions`
3. `agri-daily-monitor-schedule` -> target `agri-model-monitor`

For each schedule:

1. Schedule type: recurring.
2. Expression type: cron.
3. Set timezone and cron expression.
4. Target: Lambda function.
5. Payload: constant JSON

```json
{}
```

Suggested cron (UTC):
- inference: `cron(30 2 * * ? *)`
- curate: `cron(15 3 * * ? *)`
- monitor: `cron(0 4 * * ? *)`

### Rule D: Alarm to retraining (event pattern rule)

Page:
- `EventBridge` -> `Rules` -> `Create rule`

If the visual builder is confusing, disable `Visual rule builder opt in` and use custom JSON pattern.

Fields:
- Name: `agri-retrain-on-drift-rule`
- Event bus: `default`
- Target: Lambda `agri-start-retraining`

Event pattern JSON:

```json
{
  "source": ["aws.cloudwatch"],
  "detail-type": ["CloudWatch Alarm State Change"],
  "detail": {
    "alarmName": ["agri-overall-mape-alarm"],
    "state": {
      "value": ["ALARM"]
    }
  }
}
```

## 9) CloudWatch Alarm

Page:

- `CloudWatch` -> `Alarms` -> `Create alarm`

Step 1: Specify metric and conditions

1. Keep type as `Classic`.
2. Click `Select metric`.
3. In metric picker:
   - `Custom namespaces` -> `AgriPriceML`
   - choose dimension set containing `ModelPackageGroup`
   - select metric `OverallMAPE` with `ModelPackageGroup=agri-price-multi-output`
4. Confirm:
   - Statistic: `Average`
   - Period: `1 day`
5. Condition:
   - Threshold type: `Static`
   - Whenever `OverallMAPE` is: `Greater`
   - Threshold value: `12`
6. Additional configuration:
   - Datapoints to alarm: `2` out of `2`
   - Missing data treatment: `Not breaching` (recommended for lab)

Step 2: Configure actions

1. If SNS notification is pre-added and required, click `Remove` on the notification block.
2. Continue without SNS action.

Step 3: Add alarm details

- Alarm name: `agri-overall-mape-alarm`
- Description: `Trigger retraining when OverallMAPE exceeds threshold`

Step 4: Preview and create

- Review settings and click `Create alarm`.

## 10) Input Payload Job (Daily Requirement)

Before daily inference runs, upload payload file:

- `s3://agri-price-dev-raw/inference/input/run_date=YYYY-MM-DD/payload/features.jsonl`

And manifest file:

- `s3://agri-price-dev-raw/inference/input/run_date=YYYY-MM-DD/meta/input_manifest.parquet`

You can generate these via notebook or an ETL Lambda/Glue job.

## 11) IAM Minimum Permissions Checklist

For `agri-daily-inference`:

- `sagemaker:ListModelPackages`
- `sagemaker:CreateModel`
- `sagemaker:DescribeModel`
- `sagemaker:CreateTransformJob`
- S3 read input, S3 write output

For `agri-curate-predictions`:

- S3 read raw + meta
- S3 write curated

For `agri-model-monitor`:

- Athena start/get query
- CloudWatch put metric

For `agri-start-retraining`:

- `sagemaker:StartPipelineExecution`

All Lambdas need CloudWatch Logs write permissions.

## 12) Validation Sequence

1. Confirm one approved model package exists in `agri-price-multi-output`.
2. Upload one day payload + manifest.
3. Run `agri-daily-inference` test event `{}`.
4. Check SageMaker `Batch transform jobs` status = `Completed`.
5. Run `agri-curate-predictions` with `{"run_date":"YYYY-MM-DD"}`.
6. Run Athena `MSCK REPAIR` and `06_select_mape_by_run_date.sql`.
7. Run `agri-model-monitor`; verify CloudWatch metric appears.
8. Force alarm for test and confirm retraining starts.
