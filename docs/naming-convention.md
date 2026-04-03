# Naming Convention

This project uses a small, consistent naming pattern for the MVP term project.

## Base pattern

Use:

`<project>-<env>-<resource>`

Current values:

- Project: `agri-price`
- Environment: `dev`

## S3 bucket

- Raw bucket: `agri-price-dev-raw`

## Lambda functions

- Price ingestion Lambda: `lambda-ingest-prices`
- Weather ingestion Lambda: `lambda-ingest-weather`

## EventBridge rules

- Price schedule: `agri-price-dev-ingest-prices-schedule`
- Weather schedule: `agri-price-dev-ingest-weather-schedule`

## Data prefixes

- Raw price: `source=price/year=YYYY/month=MM/day=DD/product_id=P11001/`
- Raw weather: `source=weather/year=YYYY/month=MM/day=DD/`
- Processed features: `processed/features/`
- Model artifacts: `artifacts/model/`

## Model artifacts

Keep artifact names short and descriptive, for example:

- `xgboost-baseline.pkl`
- `feature_schema.json`
- `metrics.json`

## Rule

Do not invent extra naming variants unless a new resource type is added later.
