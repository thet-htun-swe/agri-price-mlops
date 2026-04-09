# SageMaker Pipeline CloudShell Runbook

This is the simplest practical path for this class project.

Use this approach:

1. keep preprocessing in Glue
2. upload SageMaker pipeline code to S3 manually
3. use AWS CloudShell to create the SageMaker pipeline
4. run the pipeline once manually
5. verify `Train -> Evaluate -> Register`

This avoids:

- local AWS CLI installation
- local AWS credential setup
- local SageMaker SDK upload issues

## Goal

Build the proposal-aligned cloud ML pipeline:

- `Train`
- `Evaluate`
- `Register`

with the Glue `features` dataset as input.

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

## Part A - Prepare Files Locally

### Step 1. Confirm the Glue features S3 path

Use the final Glue output path, for example:

```text
s3://agri-price-dev-raw/processed/features/
```

### Step 2. Prepare the SageMaker source archive

Create one archive containing these files:

- `train.py`
- `inference.py`
- `requirements.txt`

These come from:

- [train.py](/d:/AIT/MLOps/project/repos/agri-price-mlops/sagemaker/pipeline/train.py)
- [inference.py](/d:/AIT/MLOps/project/repos/agri-price-mlops/sagemaker/pipeline/inference.py)
- [requirements.txt](/d:/AIT/MLOps/project/repos/agri-price-mlops/sagemaker/pipeline/requirements.txt)

Suggested archive name:

```text
sagemaker_pipeline_source.tar.gz
```

### Step 3. Keep `evaluate.py` as a separate file

This file will be uploaded separately:

- [evaluate.py](/d:/AIT/MLOps/project/repos/agri-price-mlops/sagemaker/pipeline/evaluate.py)

### Step 4. Upload the SageMaker files to S3 manually

Upload these files to S3:

```text
s3://agri-price-dev-raw/sagemaker/code/sagemaker_pipeline_source.tar.gz
s3://agri-price-dev-raw/sagemaker/code/evaluate.py
s3://agri-price-dev-raw/sagemaker/code/pipeline_definition.py
```

Also upload:

- [pipeline_definition.py](/d:/AIT/MLOps/project/repos/agri-price-mlops/sagemaker/pipeline/pipeline_definition.py)

You can use the S3 console for all of these uploads.

## Part B - Create the Pipeline From CloudShell

### Step 5. Open AWS CloudShell

In the AWS Console, open:

- `CloudShell`

This is the preferred environment for this project because:

- AWS credentials are already available there
- AWS CLI is already available there
- no local setup is needed

### Step 6. Download the pipeline definition script in CloudShell

In CloudShell, run:

```bash
aws s3 cp s3://agri-price-dev-raw/sagemaker/code/pipeline_definition.py .
```

### Step 7. Install the SageMaker SDK in CloudShell if needed

Run:

```bash
python -m pip install --user sagemaker
```

If it is already available, you can skip this.

### Step 8. Generate the pipeline definition JSON in CloudShell

Run:

```bash
python pipeline_definition.py \
  --region us-east-1 \
  --role-arn arn:aws:iam::654654220088:role/LabRole \
  --bucket agri-price-dev-raw \
  --features-prefix processed/features/ \
  --pipeline-name agri-price-train-evaluate-register \
  --model-package-group-name agri-price-multi-output \
  --framework-version 1.2-1 \
  --code-bundle-s3-uri s3://agri-price-dev-raw/sagemaker/code/sagemaker_pipeline_source.tar.gz \
  --evaluate-script-s3-uri s3://agri-price-dev-raw/sagemaker/code/evaluate.py \
  --output-json pipeline-definition.json
```

### Step 9. Confirm the JSON file was created

In CloudShell, verify:

```bash
ls
```

You should see:

```text
pipeline-definition.json
```

## Part C - Create Required SageMaker Resources

### Step 10. Create the model package group

Run in CloudShell:

```bash
aws sagemaker create-model-package-group \
  --model-package-group-name agri-price-multi-output \
  --model-package-group-description "Multi-output agricultural price forecasting model"
```

If it already exists, that is fine.

## Part D - Create or Update the Pipeline

### Step 11. Create the SageMaker pipeline

Run in CloudShell:

```bash
aws sagemaker create-pipeline \
  --pipeline-name agri-price-train-evaluate-register \
  --pipeline-definition file://pipeline-definition.json \
  --role-arn arn:aws:iam::654654220088:role/LabRole
```

If the pipeline already exists, use:

```bash
aws sagemaker update-pipeline \
  --pipeline-name agri-price-train-evaluate-register \
  --pipeline-definition file://pipeline-definition.json \
  --role-arn arn:aws:iam::654654220088:role/LabRole
```

## Part E - Run the Pipeline Once

### Step 12. Start one manual pipeline execution

Run in CloudShell:

```bash
aws sagemaker start-pipeline-execution \
  --pipeline-name agri-price-train-evaluate-register
```

### Step 13. Monitor the run in SageMaker

Go to SageMaker and open the pipeline execution page.

Verify:

- training step runs
- evaluation step runs
- registration step runs

## Part F - Verify Outputs

### Step 14. Verify training output

Check:

- training job completed successfully
- model artifact exists in S3 training output

### Step 15. Verify evaluation output

Check:

- evaluation report exists
- metrics were written successfully

### Step 16. Verify registration output

Check:

- one model version exists in model package group:
  - `agri-price-multi-output`

## What Comes Next

Only after this succeeds:

1. inference from the registered model
2. prediction output to S3
3. Athena actual-vs-predicted comparison
4. Lambda monitoring metrics
5. EventBridge-triggered pipeline rerun

## Minimum Success Definition

This stage is complete when:

- SageMaker code files are uploaded to S3
- `pipeline-definition.json` is created in CloudShell
- model package group exists
- pipeline is created or updated
- one pipeline execution completes
- one model version is registered
