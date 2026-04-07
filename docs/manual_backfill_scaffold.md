# Manual Historical Backfill Scaffold

Use this scaffold when you fetch historical payloads manually from an API client and paste them into the project.

## Target Product IDs

- `P13087`
- `P13083`
- `P13043`
- `P13002`
- `P14001`

## Where To Paste Real Files

After you copy a template, place the finished files under:

- `data/raw/price/source=price/year=YYYY/month=MM/day=DD/product_id=PRODUCT_ID/...json`
- `data/raw/weather/source=weather/year=YYYY/month=MM/day=DD/...json`

`day=DD` should reflect the fetch/save date, not the historical observation date.

## Recommended Price File Naming

```text
price-PRODUCT_ID-YYYYMMDDT000000Z-manual-YYYYMM.json
```

Example:

```text
price-P13087-20260407T000000Z-manual-2022-01.json
```

## Recommended Weather File Naming

```text
weather-YYYYMMDDT000000Z-manual-YYYYMM.json
```

Example:

```text
weather-20260407T000000Z-manual-2022-01.json
```

## How To Use The Templates

1. Copy the price template that matches the product ID.
2. Replace:
   - `fetched_at_utc`
   - `from_date`
   - `to_date`
   - `http_status_code`
   - `raw_response`
3. Paste the API response JSON into `raw_response`.
4. Save the file into the correct `data/raw/...` folder.

Do the same for weather using the weather template.

## Important Rule

Paste the API response body only inside `raw_response`.

Do not replace the full wrapper object. Phase B expects the wrapper metadata fields too.
