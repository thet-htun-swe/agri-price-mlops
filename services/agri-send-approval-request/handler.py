import os
import time
import uuid
import urllib.parse
import boto3

REGION = os.environ.get("AWS_REGION", "us-east-1")
ddb = boto3.client("dynamodb", region_name=REGION)
sns = boto3.client("sns", region_name=REGION)

TABLE_NAME = os.environ["TABLE_NAME"]
TOPIC_ARN = os.environ["TOPIC_ARN"]
APPROVAL_BASE_URL = os.environ["APPROVAL_BASE_URL"]


def _build_decision_url(token: str, decision: str) -> str:
    query = urllib.parse.urlencode({"token": token, "decision": decision})
    return f"{APPROVAL_BASE_URL}?{query}"


def lambda_handler(event, context):
    execution_arn = event.get("execution_arn") or event.get("ExecutionArn")
    if not execution_arn:
        raise ValueError("Missing execution_arn in event payload.")

    token = str(uuid.uuid4())
    created_at_epoch = int(time.time())

    ddb.put_item(
        TableName=TABLE_NAME,
        Item={
            "token": {"S": token},
            "execution_arn": {"S": execution_arn},
            "status": {"S": "PENDING"},
            "created_at_epoch": {"N": str(created_at_epoch)},
        },
    )

    approve_url = _build_decision_url(token=token, decision="approve")
    reject_url = _build_decision_url(token=token, decision="reject")

    message = (
        "Data drift alarm triggered.\n\n"
        f"Step Functions execution: {execution_arn}\n\n"
        "Choose an action:\n"
        f"Approve retraining: {approve_url}\n"
        f"Reject retraining: {reject_url}\n"
    )

    sns.publish(
        TopicArn=TOPIC_ARN,
        Subject="Agri retraining approval required",
        Message=message,
    )

    return {
        "status": "sent",
        "token": token,
        "execution_arn": execution_arn,
        "approve_url": approve_url,
        "reject_url": reject_url,
    }

