-- Registers curated prediction files in S3 as a queryable table; this is your “predicted” side.

CREATE EXTERNAL TABLE IF NOT EXISTS agri_mlops.agri_predictions_curated (
  date string,
  target_next_day_price_coriander_pred double,
  target_next_day_price_kale_pred double,
  target_next_day_price_lime_pred double,
  target_next_day_price_orange_pred double,
  target_next_day_price_red_chili_pred double,
  model_package_arn string
)
PARTITIONED BY (run_date string)
STORED AS PARQUET
LOCATION 's3://agri-price-dev-raw/predictions/curated/';
