# SageMaker Pipeline Runbook

This runbook gives the exact order for setting up the proposal-aligned cloud ML pipeline.

Use this flow:

1. define the pipeline locally
2. create or update the pipeline in SageMaker
3. run it once manually
4. verify `Train -> Evaluate -> Register`
5. then move to inference and monitoring

This is the correct path for the project because:

- Glue already owns preprocessing and feature engineering
- SageMaker should own training, evaluation, registration, and automated retraining

## Files Used

Code:

- [train.py](/d:/AIT/MLOps/project/repos/agri-price-mlops/sagemaker/pipeline/train.py)
- [evaluate.py](/d:/AIT/MLOps/project/repos/agri-price-mlops/sagemaker/pipeline/evaluate.py)
- [pipeline_definition.py](/d:/AIT/MLOps/project/repos/agri-price-mlops/sagemaker/pipeline/pipeline_definition.py)
- [inference.py](/d:/AIT/MLOps/project/repos/agri-price-mlops/sagemaker/pipeline/inference.py)
- [requirements.txt](/d:/AIT/MLOps/project/repos/agri-price-mlops/sagemaker/pipeline/requirements.txt)

Reference:

- [sagemaker_pipeline_setup.md](/d:/AIT/MLOps/project/repos/agri-price-mlops/docs/sagemaker_pipeline_setup.md)
- [sagemaker_pipeline_steps.md](/d:/AIT/MLOps/project/repos/agri-price-mlops/docs/sagemaker_pipeline_steps.md)

## Part A - What You Do Locally

### Step 1. Confirm the Glue features S3 path

You need the exact S3 path for the final Phase B features dataset.

Example:

```text
s3://agri-price-dev-raw/processed/features/
```

This is the input to SageMaker training.

### Step 2. Confirm the SageMaker execution role ARN

You need the full role ARN that SageMaker can assume.

It must be able to access:

- the S3 features dataset
- SageMaker training output paths
- model package group actions

Example shape:

```text
arn:aws:iam::<account-id>:role/LabRole
```

Do not guess. Copy the exact ARN from AWS.

### Step 3. Prepare the SageMaker code files for manual S3 upload

Create one local folder copy for SageMaker upload containing:

- `train.py`
- `inference.py`
- `requirements.txt`

These come from:

- [train.py](/d:/AIT/MLOps/project/repos/agri-price-mlops/sagemaker/pipeline/train.py)
- [inference.py](/d:/AIT/MLOps/project/repos/agri-price-mlops/sagemaker/pipeline/inference.py)
- [requirements.txt](/d:/AIT/MLOps/project/repos/agri-price-mlops/sagemaker/pipeline/requirements.txt)

Compress that folder as one archive, for example:

```text
sagemaker_pipeline_source.tar.gz
```

Also keep this file separately:

- [evaluate.py](/d:/AIT/MLOps/project/repos/agri-price-mlops/sagemaker/pipeline/evaluate.py)

### Step 4. Upload the SageMaker code files to S3 manually

Upload:

- the source archive:
  - `sagemaker_pipeline_source.tar.gz`
- the evaluation script:
  - `evaluate.py`

Recommended S3 locations:

```text
s3://agri-price-dev-raw/sagemaker/code/sagemaker_pipeline_source.tar.gz
s3://agri-price-dev-raw/sagemaker/code/evaluate.py
```

### Step 5. Install the SageMaker SDK locally

In your project environment, run:

```powershell
pip install sagemaker
```

### Step 6. Generate the pipeline definition JSON

Run from repo root:

```powershell
python sagemaker\pipeline\pipeline_definition.py --region us-east-1 --role-arn arn:aws:iam::654654220088:role/LabRole --bucket agri-price-dev-raw --features-prefix processed/features/ --pipeline-name agri-price-train-evaluate-register --model-package-group-name agri-price-multi-output --framework-version 1.2-1 --code-bundle-s3-uri s3://agri-price-dev-raw/sagemaker/code/sagemaker_pipeline_source.tar.gz --evaluate-script-s3-uri s3://agri-price-dev-raw/sagemaker/code/evaluate.py --output-json .pipeline-definition.json
```

Replace:

- role ARN if it differs
- bucket or S3 paths if you use different names

What this does:

- builds the SageMaker pipeline definition from the repo code
- references pre-uploaded SageMaker code in S3 instead of auto-uploading from your laptop
- points the training step to the Glue features dataset in S3
- defines `Train -> Evaluate -> Register`

### Step 7. Confirm the JSON file was created

Verify this file exists:

- `.pipeline-definition.json`

If this file is not created successfully, stop there and fix that first.

### Step 8. Keep the pipeline code in git

Make sure these are tracked:

- `sagemaker/pipeline/train.py`
- `sagemaker/pipeline/evaluate.py`
- `sagemaker/pipeline/pipeline_definition.py`
- `sagemaker/pipeline/inference.py`
- `sagemaker/pipeline/requirements.txt`

These are now part of the project.

## Part B - What You Do In AWS

### Step 9. Create the model package group

This is needed for the `Register` step.

Preferred name:

```text
agri-price-multi-output
```

If the console allows it, create it there.

If not, use AWS CLI:

```powershell
aws sagemaker create-model-package-group `
  --model-package-group-name agri-price-multi-output `
  --model-package-group-description "Multi-output agricultural price forecasting model"
```

You only need to do this once.

### Step 10. Create or update the pipeline in SageMaker

After `.pipeline-definition.json` exists, the next step is to submit it to SageMaker.

There are multiple ways to do this:

- Python SDK
- AWS CLI

For this project, the simplest next implementation is to add a small helper script later if needed.

For now, the required checkpoint is:

- pipeline definition exists locally
- model package group exists in SageMaker

### Step 11. Run the pipeline manually once

After the pipeline is created in SageMaker, start one manual execution.

Use default parameters first unless you explicitly want to override them.

Default targets are the current multi-output targets:

- `target_next_day_price_coriander`
- `target_next_day_price_kale`
- `target_next_day_price_lime`
- `target_next_day_price_orange`
- `target_next_day_price_red_chili`

### Step 12. Verify the training step

Check that:

- the training job started
- the training job completed successfully
- model artifacts were written to S3

### Step 13. Verify the evaluation step

Check that:

- evaluation ran after training
- `evaluation.json` or equivalent evaluation output was written
- metrics are visible in the output location

### Step 14. Verify the registration step

Check that:

- a model version was created in the model package group
- approval status is present
- the artifact is linked to the registered model version

This completes the first full cloud ML pipeline run.

## Part C - What Comes Next

Only after the manual pipeline run succeeds:

1. build prediction flow from the registered model
2. save predictions to S3
3. compare actual vs predicted using Athena
4. compute monitoring metrics with Lambda
5. trigger the SageMaker pipeline automatically with EventBridge

## What Not To Do Yet

Do not build these first:

- web UI
- endpoint deployment
- drift alarms
- retraining trigger

Those depend on the SageMaker pipeline working first.

## Minimum Success Definition

You are done with this stage when:

- the SageMaker code archive and evaluation script are uploaded to S3
- `.pipeline-definition.json` is generated locally
- the model package group exists in SageMaker
- the SageMaker pipeline is created
- one manual pipeline execution completes
- the model is registered successfully

## Notes

- local training is now only a prototype/debug path
- Glue remains the official feature-engineering step
- SageMaker becomes the official cloud training path
