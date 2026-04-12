import os
import boto3

REGION = os.environ.get("AWS_REGION", "us-east-1")
sm = boto3.client("sagemaker", region_name=REGION)

PIPELINE_NAME = os.environ["PIPELINE_NAME"]
TARGET_COLUMNS = os.environ["TARGET_COLUMNS"]
FEATURES_S3_URI = os.environ["FEATURES_S3_URI"]

def lambda_handler(event, context):
    resp = sm.start_pipeline_execution(
        PipelineName=PIPELINE_NAME,
        PipelineParameters=[
            {"Name": "TargetColumns", "Value": TARGET_COLUMNS},
            {"Name": "FeaturesS3Uri", "Value": FEATURES_S3_URI},
        ],
    )
    return {"status": "started", "pipeline_execution_arn": resp["PipelineExecutionArn"]}