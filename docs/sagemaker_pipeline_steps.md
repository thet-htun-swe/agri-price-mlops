# SageMaker Pipeline Steps

This guide is the practical step-by-step path for the proposal-aligned cloud ML pipeline.

Use this flow:

1. keep Phase B in Glue
2. move Phase C train/evaluate/register into SageMaker
3. later connect monitoring and automated retraining

## Files Added For This Stage

Code:

- [train.py](/d:/AIT/MLOps/project/repos/agri-price-mlops/sagemaker/pipeline/train.py)
- [evaluate.py](/d:/AIT/MLOps/project/repos/agri-price-mlops/sagemaker/pipeline/evaluate.py)
- [pipeline_definition.py](/d:/AIT/MLOps/project/repos/agri-price-mlops/sagemaker/pipeline/pipeline_definition.py)
- [inference.py](/d:/AIT/MLOps/project/repos/agri-price-mlops/sagemaker/pipeline/inference.py)
- [requirements.txt](/d:/AIT/MLOps/project/repos/agri-price-mlops/sagemaker/pipeline/requirements.txt)

Reference:

- [sagemaker_pipeline_setup.md](/d:/AIT/MLOps/project/repos/agri-price-mlops/docs/sagemaker_pipeline_setup.md)

## What You Need To Do Manually

### 1. Confirm the features S3 path

You need the exact S3 prefix for the Glue output dataset, for example:

```text
s3://agri-price-dev-raw/processed/features/
```

This is the training input for SageMaker.

### 2. Confirm the SageMaker execution role

You need one role ARN that SageMaker can use.

It must be able to access:

- the Glue-built features path
- SageMaker training output paths
- model package group actions

In Learner Lab this is often `LabRole`, but confirm the actual ARN in IAM or SageMaker.

### 3. Prepare the SageMaker code bundle locally

Create one archive containing:

- `train.py`
- `inference.py`
- `requirements.txt`

Then upload that archive to S3 manually.

Also upload:

- `evaluate.py`

Recommended S3 locations:

```text
s3://agri-price-dev-raw/sagemaker/code/sagemaker_pipeline_source.tar.gz
s3://agri-price-dev-raw/sagemaker/code/evaluate.py
```

### 4. Install the SageMaker SDK locally

Run in your project environment:

```powershell
pip install sagemaker
```

If your environment is managed another way, install it there first.

### 5. Generate the pipeline definition

Run from repo root:

```powershell
python sagemaker\pipeline\pipeline_definition.py --region us-east-1 --role-arn <YOUR_SAGEMAKER_ROLE_ARN> --bucket <YOUR_BUCKET_NAME> --features-prefix processed/features/ --pipeline-name agri-price-train-evaluate-register --model-package-group-name agri-price-multi-output --framework-version 1.2-1 --code-bundle-s3-uri s3://<YOUR_BUCKET_NAME>/sagemaker/code/sagemaker_pipeline_source.tar.gz --evaluate-script-s3-uri s3://<YOUR_BUCKET_NAME>/sagemaker/code/evaluate.py --output-json .pipeline-definition.json
```

What this does:

- creates a SageMaker pipeline definition
- uses pre-uploaded code from S3 so local AWS credentials are not needed for code packaging
- points training at Glue output in S3
- defines `Train -> Evaluate -> Register`

### 6. Create the model package group

Do this once.

If you can use console:

- create model package group named `agri-price-multi-output`

If console does not expose it, use AWS CLI:

```powershell
aws sagemaker create-model-package-group `
  --model-package-group-name agri-price-multi-output `
  --model-package-group-description "Multi-output agricultural price forecasting model"
```

### 7. Create or update the SageMaker pipeline

Use the SageMaker SDK route from Python or AWS CLI once you have the definition.

Simplest next implementation path is to create a small script later to upsert the pipeline.

For now, the required manual checkpoint is:

- confirm `.pipeline-definition.json` was generated successfully

### 8. Run the pipeline manually once

After the pipeline exists, run it manually with:

- default target columns, or
- an explicit comma-separated target list if needed

Default targets currently are:

- `target_next_day_price_coriander`
- `target_next_day_price_kale`
- `target_next_day_price_lime`
- `target_next_day_price_orange`
- `target_next_day_price_red_chili`

### 9. Verify training output

After the run, verify:

- training step completed
- evaluation step produced an evaluation report
- registration step created a model package version

### 10. Only after this, move to inference and monitoring

Do not build:

- web UI
- CloudWatch monitoring
- EventBridge retraining trigger

until the SageMaker pipeline runs once successfully.

## Important Notes

### About preprocessing

Do not add a SageMaker preprocessing step now.

Glue already owns:

- cleaning
- feature engineering
- Parquet output

That is enough.

### About local training

The local model remains useful for:

- quick debugging
- feature sanity checks
- comparing logic

But it is not the final automated retraining path.

## What To Expect Next

After this SageMaker pipeline works, the next tasks are:

1. run inference from the registered model
2. store predictions in S3
3. join predictions with actuals in Athena
4. compute monitoring metrics
5. trigger pipeline reruns with EventBridge
