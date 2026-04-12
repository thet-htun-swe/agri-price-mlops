import os
import boto3
from datetime import datetime, timezone

REGION = os.environ.get("AWS_REGION", "us-east-1")
sm = boto3.client("sagemaker", region_name=REGION)

MODEL_PACKAGE_GROUP = os.environ["MODEL_PACKAGE_GROUP"]
SAGEMAKER_EXEC_ROLE_ARN = os.environ["SAGEMAKER_EXEC_ROLE_ARN"]

INPUT_S3_URI_TEMPLATE = os.environ["INPUT_S3_URI_TEMPLATE"]
OUTPUT_S3_URI_TEMPLATE = os.environ["OUTPUT_S3_URI_TEMPLATE"]

INSTANCE_TYPE = os.environ.get("INSTANCE_TYPE", "ml.m5.large")
INSTANCE_COUNT = int(os.environ.get("INSTANCE_COUNT", "1"))

def _latest_approved_model_package_arn():
    resp = sm.list_model_packages(
        ModelPackageGroupName=MODEL_PACKAGE_GROUP,
        ModelApprovalStatus="Approved",
        SortBy="CreationTime",
        SortOrder="Descending",
        MaxResults=1,
    )
    items = resp.get("ModelPackageSummaryList", [])
    if not items:
        raise RuntimeError(f"No Approved model package found in {MODEL_PACKAGE_GROUP}")
    return items[0]["ModelPackageArn"]

def _model_name_from_pkg_arn(pkg_arn: str) -> str:
    version = pkg_arn.rstrip("/").split("/")[-1]
    return f"agri-price-infer-v{version}"

def _ensure_model_exists(model_name: str, model_package_arn: str):
    try:
        sm.describe_model(ModelName=model_name)
    except sm.exceptions.ClientError as e:
        msg = str(e)
        if "Could not find model" in msg or "ValidationException" in msg:
            sm.create_model(
                ModelName=model_name,
                ExecutionRoleArn=SAGEMAKER_EXEC_ROLE_ARN,
                Containers=[{"ModelPackageName": model_package_arn}],
            )
        else:
            raise

def lambda_handler(event, context):
    run_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    run_stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")

    model_package_arn = _latest_approved_model_package_arn()
    model_name = _model_name_from_pkg_arn(model_package_arn)
    _ensure_model_exists(model_name, model_package_arn)

    input_s3 = INPUT_S3_URI_TEMPLATE.format(run_date=run_date)
    output_s3 = OUTPUT_S3_URI_TEMPLATE.format(run_date=run_date)

    transform_job_name = f"agri-price-batch-predict-{run_stamp}"

    sm.create_transform_job(
        TransformJobName=transform_job_name,
        ModelName=model_name,
        TransformInput={
            "DataSource": {"S3DataSource": {"S3DataType": "S3Prefix", "S3Uri": input_s3}},
            "ContentType": "application/json",
            "SplitType": "Line",
        },
        TransformOutput={
            "S3OutputPath": output_s3,
            "Accept": "application/json",
            "AssembleWith": "Line",
        },
        TransformResources={"InstanceType": INSTANCE_TYPE, "InstanceCount": INSTANCE_COUNT},
        BatchStrategy="SingleRecord",
        MaxPayloadInMB=1,
    )

    return {
        "status": "started",
        "run_date": run_date,
        "model_package_arn": model_package_arn,
        "model_name": model_name,
        "transform_job_name": transform_job_name,
        "input_s3": input_s3,
        "output_s3": output_s3,
    }