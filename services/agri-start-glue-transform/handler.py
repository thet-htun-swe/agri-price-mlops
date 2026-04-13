import os
import boto3

glue = boto3.client("glue", region_name=os.environ.get("AWS_REGION", "us-east-1"))
JOB_NAME = os.environ["GLUE_JOB_NAME"]

def lambda_handler(event, context):
    resp = glue.start_job_run(JobName=JOB_NAME)
    return {"status": "started", "job_name": JOB_NAME, "job_run_id": resp["JobRunId"]}
