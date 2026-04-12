# SageMaker Studio Notebook Runbook

This is the SageMaker Studio notebook path for this project.

Use this path if you want to work closer to the lab document:

1. create SageMaker domain
2. create user profile
3. launch Studio
4. open a notebook
5. run the notebook to upload code, create or update the pipeline, and start one execution

This still follows the proposal because:

- Glue remains the preprocessing layer
- SageMaker handles `Train -> Evaluate -> Register`
- later EventBridge can trigger the pipeline automatically

## What This Method Is Good For

Use the Studio notebook method when:

- you prefer a notebook workflow
- you want AWS-authenticated execution without local credential setup
- you want a simpler place to debug SageMaker code

## Files Used

- [sagemaker_pipeline_studio_setup.ipynb](/d:/AIT/MLOps/project/repos/agri-price-mlops/notebooks/sagemaker_pipeline_studio_setup.ipynb)
- [pipeline_definition.py](/d:/AIT/MLOps/project/repos/agri-price-mlops/sagemaker/pipeline/pipeline_definition.py)
- [train.py](/d:/AIT/MLOps/project/repos/agri-price-mlops/sagemaker/pipeline/train.py)
- [evaluate.py](/d:/AIT/MLOps/project/repos/agri-price-mlops/sagemaker/pipeline/evaluate.py)
- [inference.py](/d:/AIT/MLOps/project/repos/agri-price-mlops/sagemaker/pipeline/inference.py)
- [requirements.txt](/d:/AIT/MLOps/project/repos/agri-price-mlops/sagemaker/pipeline/requirements.txt)

## Part A - AWS Console Setup

### Step 1. Create a SageMaker domain

Go to:

- AWS Console
- SageMaker AI
- `Domains`
- `Create domain`

Use the simplest allowed setup in your lab account.

### Step 2. Create a user profile

After domain creation:

- create one user profile

### Step 3. Launch SageMaker Studio

Open Studio from that user profile.

### Step 4. Create a notebook

Create a notebook using a standard Python or Data Science image.

If the lab specifically mentions `ipykernel`, use that kernel.

## Part B - Get the Notebook Into Studio

### Step 5. Upload the notebook file only

Upload this single file into Studio:

- [sagemaker_pipeline_studio_setup.ipynb](/d:/AIT/MLOps/project/repos/agri-price-mlops/notebooks/sagemaker_pipeline_studio_setup.ipynb)

### Step 6. Open the notebook

Open the uploaded file:

- `sagemaker_pipeline_studio_setup.ipynb`

## Part C - Run the Notebook

### Step 7. Install the correct SageMaker SDK version in the notebook

The notebook includes a cell to install:

```python
%pip install "sagemaker<3"
```

This is intentional. The project uses the classic SageMaker SDK line.

### Step 8. Set project variables

The notebook includes one configuration cell where you fill:

- bucket name
- role ARN
- features S3 path
- pipeline name
- model package group name

### Step 9. Upload the SageMaker code bundle from the notebook

The notebook will:

- create `sagemaker_pipeline_source.tar.gz`
- upload it to S3
- upload `evaluate.py`

This removes the need for local AWS CLI or CloudShell uploads.

### Step 10. Create the model package group

The notebook will:

- create the model package group if it does not already exist

### Step 11. Create or update the SageMaker pipeline

The notebook will:

- build the pipeline object
- upsert the pipeline in SageMaker

### Step 12. Start one pipeline execution

The notebook will:

- start one execution
- print the pipeline execution ARN

### Step 13. Monitor the execution

The notebook also includes cells to:

- list pipeline executions
- list execution steps

Use those cells first before going to console pages.

## Part D - What You Verify

After running the notebook, verify:

1. training step succeeded
2. evaluation step succeeded
3. registration step succeeded
4. a model version exists in:
   - `agri-price-multi-output`

## Important Notes

### About local prototype code

The notebook still reuses parts of the project codebase.

That is acceptable because the actual training execution is still happening in SageMaker, not on your laptop.

### About current failures

If the current train step keeps failing because of package incompatibility, the next fix should be made in:

- `sagemaker/pipeline/train.py`
- `sagemaker/pipeline/requirements.txt`

The notebook is the easier place to debug those runs.

## Recommended Use

Use this notebook path as the main setup method now.

It is closer to the lab flow and simpler than mixing:

- local machine
- CloudShell
- partial manual packaging

## What Comes Next

Only after the notebook creates a successful pipeline run:

1. inference from registered model
2. prediction outputs to S3
3. Athena actual-vs-predicted comparison
4. CloudWatch monitoring
5. EventBridge-triggered retraining

Detailed runbook:

- [sagemaker_inference_monitoring_runbook.md](/d:/AIT/MLOps/project/repos/agri-price-mlops/docs/sagemaker_inference_monitoring_runbook.md)
- [production_inference_drift_pipeline_runbook.md](/d:/AIT/MLOps/project/repos/agri-price-mlops/docs/production_inference_drift_pipeline_runbook.md)
