# Phase B MVP

Phase B is implemented as one shared transformation module plus two entrypoints:

- local run: `scripts/build_daily_features.py`
- Glue run: `glue/jobs/build_daily_features_job.py`

Both paths produce the same processed datasets.

## Goal

Create one reliable daily feature dataset with one row per date and stable machine-friendly columns for downstream XGBoost training.

## Inputs

- raw price JSON files
- raw weather JSON files
- explicit mapping tables in `data/product_mapping/`
  - `mapping_name.csv`
  - `category_mapping.csv`
  - `group_mapping.csv`
  - `unit_mapping.csv`

## Outputs

The processed root contains three Parquet datasets:

- `clean_prices/`
- `clean_weather/`
- `features/`

The `features/` dataset also writes metadata under `_meta/`:

- `validation_report.json`
- `feature_schema.json`

## Transformation behavior

- Standardizes date parsing to daily granularity.
- Normalizes Thai text fields and translates mapped categorical values to English.
- Deduplicates raw price rows to one row per `date` and `product_id`, keeping the latest fetch.
- Deduplicates weather rows to one row per `date`, keeping the latest fetch.
- Reshapes prices from long format to wide columns such as `price_coriander`.
- Reindexes to a continuous daily date range.
- Applies forward fill only to base weather and price columns, with a default limit of 7 days.
- Adds missingness indicator columns such as `price_coriander_was_missing`.
- Generates lag features, rolling means, calendar features, and next-day target columns.
- Writes Parquet partitioned by `year` and `month`.

## Local run

From the repo root:

```bash
python scripts/build_daily_features.py \
  --price-dir data/raw/price \
  --weather-dir data/raw/weather \
  --mapping-dir data/product_mapping \
  --output-root data/processed
```

Optional knobs:

- `--lags 1,7,14,28`
- `--rolling-windows 3,7,14`
- `--forward-fill-limit 7`
- `--target-horizon-days 1`

## Glue run

Example Glue arguments:

```text
--raw-bucket agri-price-dev-raw
--price-prefix source=price/
--weather-prefix source=weather/
--processed-bucket agri-price-dev-raw
--processed-prefix processed
--mapping-prefix reference/product_mapping/
```

The Glue job uploads:

- `processed/clean_prices/year=.../month=.../`
- `processed/clean_weather/year=.../month=.../`
- `processed/features/year=.../month=.../`
- `processed/features/_meta/validation_report.json`
- `processed/features/_meta/feature_schema.json`

## Validation checks

The job fails if any of these checks fail:

- duplicate dates in `features`
- duplicate `date` and `product_id` rows in `clean_prices`
- duplicate dates in `clean_weather`
- invalid column names
- missing required feature columns
- missing `year` or `month` partition columns

Expected missing values are documented in `features/_meta/validation_report.json`.
