import os
import boto3

REGION = os.environ.get("AWS_REGION", "us-east-1")
ddb = boto3.client("dynamodb", region_name=REGION)

TABLE_NAME = os.environ["TABLE_NAME"]


def lambda_handler(event, context):
    token = event.get("token")
    task_token = event.get("task_token")
    if not token or not task_token:
        raise ValueError("Both token and task_token are required.")

    ddb.update_item(
        TableName=TABLE_NAME,
        Key={"token": {"S": token}},
        UpdateExpression="SET task_token = :task_token",
        ExpressionAttributeValues={":task_token": {"S": task_token}},
        ConditionExpression="attribute_exists(token)",
    )

    return {"status": "stored", "token": token}

