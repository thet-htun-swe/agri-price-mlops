import json
import os
import boto3

REGION = os.environ.get("AWS_REGION", "us-east-1")
ddb = boto3.client("dynamodb", region_name=REGION)
sfn = boto3.client("stepfunctions", region_name=REGION)

TABLE_NAME = os.environ["TABLE_NAME"]


def _response(status_code: int, body: str):
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "text/plain; charset=utf-8"},
        "body": body,
    }


def lambda_handler(event, context):
    query = event.get("queryStringParameters") or {}
    token = query.get("token")
    decision = (query.get("decision") or "").lower()
    if not token or decision not in ("approve", "reject"):
        return _response(400, "Invalid request. token and decision=approve|reject are required.")

    item = ddb.get_item(TableName=TABLE_NAME, Key={"token": {"S": token}}).get("Item")
    if not item:
        return _response(404, "Approval token not found.")

    task_token = (item.get("task_token") or {}).get("S")
    if not task_token:
        return _response(409, "Task token is not ready yet. Please try again shortly.")

    status = "APPROVED" if decision == "approve" else "REJECTED"
    if decision == "approve":
        sfn.send_task_success(
            taskToken=task_token,
            output=json.dumps({"approved": True, "token": token}),
        )
    else:
        sfn.send_task_failure(
            taskToken=task_token,
            error="ApprovalRejected",
            cause="Manual rejection from human-in-the-loop endpoint",
        )

    ddb.update_item(
        TableName=TABLE_NAME,
        Key={"token": {"S": token}},
        UpdateExpression="SET #status = :status",
        ExpressionAttributeNames={"#status": "status"},
        ExpressionAttributeValues={":status": {"S": status}},
    )

    return _response(200, f"Decision recorded: {status}")

