CREATE EXTERNAL TABLE IF NOT EXISTS agri_mlops.agri_features_actual (
  date string,
  target_next_day_price_coriander double,
  target_next_day_price_kale double,
  target_next_day_price_lime double,
  target_next_day_price_orange double,
  target_next_day_price_red_chili double
)
PARTITIONED BY (year int, month int)
STORED AS PARQUET
LOCATION 's3://agri-price-dev-raw/processed/features/';
