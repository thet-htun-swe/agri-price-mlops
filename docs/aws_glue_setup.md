# AWS Glue Setup for Phase B

This guide assumes you are using the current repo design:

- job script: [build_daily_features_job.py](D:/AIT/MLOps/project/repos/agri-price-mlops/glue/jobs/build_daily_features_job.py)
- helper module: [phase_b_transform.py](D:/AIT/MLOps/project/repos/agri-price-mlops/glue/jobs/phase_b_transform.py)
- mapping files: [data/product_mapping](D:/AIT/MLOps/project/repos/agri-price-mlops/data/product_mapping)

It also assumes you cannot create a new IAM role and will try to use `LabRole`.

## 1. Files You Need

Prepare these files on your machine:

- `build_daily_features_job.py`
- `glue_package.zip`
- mapping CSV files:
  - `mapping_name.csv`
  - `category_mapping.csv`
  - `group_mapping.csv`
  - `unit_mapping.csv`

## 2. Create `glue_package.zip`

Use normal file explorer, not CLI.

The zip should contain:

```text
glue/
  jobs/
    phase_b_transform.py
```

It does **not** need:
- `build_daily_features_job.py`
- mapping CSV files

## 3. Upload Files to S3

Use the S3 Console.

Upload these objects:

```text
s3://agri-price-dev-raw/glue/build_daily_features_job.py
s3://agri-price-dev-raw/glue/glue_package.zip
s3://agri-price-dev-raw/reference/product_mapping/mapping_name.csv
s3://agri-price-dev-raw/reference/product_mapping/category_mapping.csv
s3://agri-price-dev-raw/reference/product_mapping/group_mapping.csv
s3://agri-price-dev-raw/reference/product_mapping/unit_mapping.csv
```

## 4. Open AWS Glue

Go to:

- AWS Console
- AWS Glue
- Jobs
- Create job
- Script editor

In the modal:

- `Engine`: `Spark`
- `Option`: `Upload script`
- Upload: `build_daily_features_job.py`

Then click `Create script`.

## 5. Fill the Glue Job Details

Use values like these.

### Basic Properties

- `Name`: `agri-price-dev-phase-b`
- `IAM role`: `LabRole`
- `Glue version`: `5.1` if available, otherwise `5.0`
- `Worker type`: `G.1X`
- `Number of workers`: `2`

Do not choose:
- Python shell
- Ray

## 6. Set the Script Path

After the editor opens, set these fields correctly:

```text
Script filename: build_daily_features_job.py
Script path: s3://aws-glue-assets-<account-id>-<region>/scripts/
```

Important:

- `Script filename` is the file name
- `Script path` is the S3 folder path
- do not put the full file path into `Script path`

If you use the Glue default script path, that is okay. Glue will save the script there.

## 7. Add Job Parameters

In Job details / Advanced properties / Default arguments, add:

```text
--raw-bucket=agri-price-dev-raw
--price-prefix=source=price/
--weather-prefix=source=weather/
--processed-bucket=agri-price-dev-raw
--processed-prefix=processed
--mapping-prefix=reference/product_mapping/
--TempDir=s3://agri-price-dev-raw/glue/tmp/
--extra-py-files=s3://agri-price-dev-raw/glue/glue_package.zip
```

Optional tuning:

```text
--lags=1,7,14,28
--rolling-windows=3,7,14
--forward-fill-limit=7
--target-horizon-days=1
```

## 8. Save and Run

Click:

- `Save`
- `Run`

## 9. What Success Looks Like

If the run succeeds, you should see:

```text
s3://agri-price-dev-raw/processed/clean_prices/year=.../month=.../
s3://agri-price-dev-raw/processed/clean_weather/year=.../month=.../
s3://agri-price-dev-raw/processed/features/year=.../month=.../
s3://agri-price-dev-raw/processed/features/_meta/validation_report.json
s3://agri-price-dev-raw/processed/features/_meta/feature_schema.json
```

## 10. Validate the Result

Open:

- `processed/features/_meta/validation_report.json`
- `processed/features/_meta/feature_schema.json`

Check:

- `status` is `passed`
- `duplicate_dates` is `0`
- no required columns are missing

## 11. If the Job Fails

### Error: cannot select or use `LabRole`

Cause:
- Learner Lab permissions do not allow Glue to use it

Fix:
- try the role anyway if selectable
- if not selectable, the lab account is blocking that path

### Error: `ModuleNotFoundError`

Cause:
- `--extra-py-files` missing or wrong S3 path

Fix:
- confirm:
  - `s3://agri-price-dev-raw/glue/glue_package.zip`
- confirm the zip contains:
  - `glue/jobs/phase_b_transform.py`

### Error: S3 access denied

Cause:
- `LabRole` lacks S3 permissions

Fix:
- verify `LabRole` can access:
  - raw prefixes
  - processed prefix
  - script path
  - temp dir

### Error: no JSON payloads found

Cause:
- wrong prefixes

Fix:
- confirm raw files are really under:
  - `source=price/`
  - `source=weather/`

## 12. Notes

- AWS Glue jobs require an IAM role. If you cannot create one, using `LabRole` is the correct attempt.
- Glue expects imported helper code to be provided through S3 when you use `--extra-py-files`.
- Glue scripts are stored in S3 by design.
- `--TempDir` should point to an S3 path used as a temporary directory.

## Sources

- IAM role for Glue: https://docs.aws.amazon.com/glue/latest/dg/create-an-iam-role.html
- Python files with `--extra-py-files`: https://docs.aws.amazon.com/glue/latest/dg/aws-glue-programming-python-libraries.html
- Job arguments including `--TempDir`: https://docs.aws.amazon.com/glue/latest/dg/aws-glue-programming-etl-glue-arguments.html
- Glue versions: https://docs.aws.amazon.com/glue/latest/dg/release-notes.html
- Notebook/job scripts saved to S3: https://docs.aws.amazon.com/glue/latest/dg/save-notebook.html
