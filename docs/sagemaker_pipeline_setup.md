# SageMaker Pipeline Setup

This document defines the proposal-aligned cloud ML pipeline for this project.

Canonical execution path: SageMaker Studio notebook runbook.

The key rule is:

- Glue handles feature engineering
- SageMaker handles train, evaluate, register
- EventBridge and CloudWatch handle automated retraining

This replaces the earlier idea of treating the local-trained artifact as the final production path.

## 1. Target Design

Use a minimal SageMaker Pipeline with only these ML stages:

1. `Train`
2. `Evaluate`
3. `Register`

Do not rebuild Phase B preprocessing inside SageMaker.

Reason:

- Phase B is already implemented in AWS Glue
- the proposal requires automation, not duplication
- keeping preprocessing in Glue is simpler and cleaner

## 2. End-to-End Cloud Flow

The intended final flow is:

1. Lambda ingests raw price and weather data into S3
2. Glue transforms raw data into the curated `features` dataset
3. SageMaker Pipeline reads the `features` dataset from S3
4. SageMaker training step trains the model
5. SageMaker evaluation step scores the model
6. SageMaker registration step registers the model version
7. Deployment or batch inference writes predictions
8. Athena and Lambda compare predictions vs actual prices
9. CloudWatch alarm or EventBridge triggers retraining
10. SageMaker Pipeline runs again automatically

## 3. Why This Is the Correct Proposal Fit

This design satisfies the automated retraining requirement because:

- training runs in the cloud
- registration runs in the cloud
- retraining can be triggered automatically by AWS services

Using only a local-trained artifact would not satisfy the proposal's full automated retraining loop.

## 4. Pipeline Inputs

The SageMaker Pipeline should consume:

- the `features` dataset from S3
- target columns from the processed feature table
- model hyperparameters

Current target columns:

- `target_next_day_price_coriander`
- `target_next_day_price_kale`
- `target_next_day_price_lime`
- `target_next_day_price_orange`
- `target_next_day_price_red_chili`

## 5. Pipeline Outputs

The pipeline should produce:

- trained model artifact
- evaluation report
- model registration entry

Recommended output locations:

- training output S3 prefix
- evaluation report S3 prefix
- SageMaker Model Registry model package group

## 6. Minimal Train Step

The training step should:

1. read the prepared features dataset from S3
2. split data using time-aware logic
3. train the current multi-output forecasting model
4. save the model artifact and basic metadata

This step can reuse the existing local Phase C logic, but it must run inside SageMaker, not on the laptop.

## 7. Minimal Evaluate Step

The evaluation step should:

1. load the trained model artifact
2. evaluate on the held-out validation or test data
3. write an evaluation JSON report to S3

At minimum, record:

- overall MAE
- overall RMSE
- per-target metrics
- comparison against baseline if implemented in the training image

## 8. Minimal Register Step

The registration step should:

1. read the evaluation report
2. register the trained model in SageMaker Model Registry
3. create a version in a model package group

Recommended model package group name:

```text
agri-price-multi-output
```

## 9. Deployment After Registration

After registration, deployment can be done separately.

For this project, deployment can stay simple:

- one endpoint or
- one batch inference flow

The key point is that the registered model version becomes the deployment source.

## 10. Retraining Trigger Design

The retraining loop should work like this:

1. predictions are written to S3
2. actual observed prices are available in processed data
3. Athena joins actual vs predicted
4. Lambda computes metrics such as MAE, RMSE, or MAPE
5. Lambda publishes metrics to CloudWatch
6. CloudWatch alarm fires when threshold is breached
7. EventBridge triggers a new SageMaker Pipeline execution

AWS supports triggering SageMaker Pipelines with EventBridge:

- https://docs.aws.amazon.com/sagemaker/latest/dg/pipeline-eventbridge.html
- https://docs.aws.amazon.com/sagemaker/latest/dg/automating-sagemaker-with-eventbridge.html

## 11. What Stays Useful From Local Training

The local-trained model is still useful for:

- validating dataset readiness
- validating the Phase C logic
- debugging model code quickly

But it should be treated as:

- development validation
- not the final proposal-compliant retraining path

## 12. Recommended Implementation Order

1. convert current training code into SageMaker-compatible train script
2. create evaluation script
3. define the SageMaker Pipeline with `Train -> Evaluate -> Register`
4. create the model package group
5. run the pipeline manually once
6. define inference output storage
7. build actual-vs-predicted monitoring
8. wire CloudWatch and EventBridge retraining trigger

## 13. What Not To Do

Do not build a large SageMaker preprocessing step if Glue already owns Phase B.

Do not keep the final retraining path dependent on local or manual training.

Do not spend time on model tuning before the cloud train, evaluate, and register flow exists.

## 14. Minimum Completion Definition

This stage is complete when:

- SageMaker training runs from S3 features
- SageMaker evaluation writes a report
- SageMaker registration creates a model version
- a rerun can be triggered by AWS services without manual local training

## 15. Related Docs

- [sagemaker_studio_notebook_runbook.md](/d:/AIT/MLOps/project/repos/agri-price-mlops/docs/sagemaker_studio_notebook_runbook.md)
- [aws_glue_setup.md](/d:/AIT/MLOps/project/repos/agri-price-mlops/docs/aws_glue_setup.md)
- [phase_c_setup.md](/d:/AIT/MLOps/project/repos/agri-price-mlops/docs/phase_c_setup.md)
- [next_pipeline_steps.md](/d:/AIT/MLOps/project/repos/agri-price-mlops/docs/next_pipeline_steps.md)
