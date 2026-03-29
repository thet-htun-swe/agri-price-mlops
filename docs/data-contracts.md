Raw S3 Layout

Raw price data
s3://agri-price-dev-raw/source=price/year={YYYY}/month={MM}/day={DD}/product_id={PRODUCT_ID}/

Example:
s3://agri-price-dev-raw/source=price/year=2026/month=03/day=29/product_id=P11001/

Stored file pattern:

price-{product_id}-{timestamp}-{uuid}.json

Example:
price-P11001-20260329T101500Z-123e4567.json

Raw weather data
s3://agri-price-dev-raw/source=weather/year={YYYY}/month={MM}/day={DD}/

Example:
s3://agri-price-dev-raw/source=weather/year=2026/month=03/day=29/

Stored file pattern:
weather-{timestamp}-{uuid}.json
