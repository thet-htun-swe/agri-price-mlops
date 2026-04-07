# Next Pipeline Steps

This document records the current pipeline state and the next proposal-aligned work items, so the project can be resumed cleanly after a break.

## Current State

Completed:

- raw historical price data collected
- raw historical weather data collected
- Phase B feature engineering completed
- Glue job for Phase B created and run successfully
- processed dataset rebuilt from the historical raw data
- Phase C model training completed
- one multi-output model artifact created for all target products
- walk-forward comparison report generated

Current trained target columns:

- `target_next_day_price_coriander`
- `target_next_day_price_kale`
- `target_next_day_price_lime`
- `target_next_day_price_orange`
- `target_next_day_price_red_chili`

Current training outputs:

- `artifacts/model/model.pkl`
- `artifacts/model/metrics.json`
- `artifacts/model/training_summary.json`
- `artifacts/model/comparison_report.json`

## Important Interpretation

The pipeline works end to end through training.

However, the current learned model does not beat the persistence baseline yet. That is a model-quality issue, not a pipeline-completeness issue.

Because this project is focused on Data Engineering and MLOps, the next work should prioritize operational pipeline completion rather than model tuning.

## Next Recommended Order

### 1. Inference Flow

Build the prediction path that:

- loads `model.pkl`
- reads processed feature rows for inference
- outputs predicted prices for all target products
- writes prediction results to S3 or local output

Deliverable:

- one reproducible prediction script

### 2. Model Packaging for SageMaker

Prepare the trained artifact for SageMaker use:

- finalize artifact packaging format
- upload model artifact to S3
- record artifact URI

Deliverable:

- S3-hosted model artifact ready for registration

### 3. SageMaker Model Registry

Register the current trained model:

- create a model package group
- register the multi-output model artifact
- record model version metadata

Deliverable:

- one registered SageMaker model version

### 4. Deployment Path

Define how the model will be served:

- batch inference path or endpoint path
- expected input schema
- expected output schema

Deliverable:

- one documented serving approach

### 5. Prediction Logging

Save model outputs in a structured format including:

- prediction date
- generated_at timestamp
- predicted prices for all products
- model artifact or version identifier

Deliverable:

- prediction log dataset

### 6. Actual vs Predicted Comparison

Build a dataset or query path that compares:

- predictions
- later actual observed prices

Likely implementation:

- Athena query over predictions + processed actuals

Deliverable:

- actual-vs-predicted comparison table or query

### 7. Monitoring Metrics

Add monitoring that computes:

- MAE
- RMSE
- drift/degradation signals if needed

Deliverable:

- CloudWatch metrics or equivalent monitoring output

### 8. Retraining Trigger

Add a simple retraining path:

- scheduled retraining or
- threshold-triggered retraining

Deliverable:

- one documented retraining mechanism

## Immediate Next Task

The next concrete implementation should be:

- build the inference script and prediction output schema

That is the shortest path from “trained model exists” to “operational MLOps pipeline exists”.
