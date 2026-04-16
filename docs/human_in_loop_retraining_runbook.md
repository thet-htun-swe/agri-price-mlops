# Human-in-the-Loop Retraining Runbook

This runbook adds manual approval before retraining.

Flow:
1. CloudWatch alarm detects drift.
2. EventBridge starts Step Functions.
3. Step Functions sends approval request to admin.
4. Admin clicks Approve/Reject link.
5. Step Functions either starts retraining or exits.

---

## 0) Prerequisites

Confirm these already exist:
- CloudWatch alarm: `agri-overall-mape-alarm`
- SageMaker start-retrain Lambda: `agri-start-retraining`
- IAM role usable by Lambda/Step Functions (for example `LabRole`)

---

## 1) Create SNS Topic (Admin Notification)

1. Open **Amazon SNS**.
2. Left menu: **Topics**.
3. Click **Create topic**.
4. Type: `Standard`.
5. Name: `agri-retrain-approval-topic`.
6. Click **Create topic**.
7. In topic page, click **Create subscription**.
8. Protocol: `Email`.
9. Endpoint: your admin email.
10. Click **Create subscription**.
11. Open email inbox and click confirmation link.

---

## 2) Create DynamoDB Table (Approval Token Store)

1. Open **DynamoDB**.
2. Click **Create table**.
3. Table name: `agri-retrain-approvals`.
4. Partition key: `token` (String).
5. Keep defaults.
6. Click **Create table**.

---

## 3) Create Lambda: `agri-send-approval-request`

Purpose:
- Generate approval token.
- Store token in DynamoDB.
- Send email with Approve/Reject links.

1. Open **Lambda**.
2. Click **Create function**.
3. Choose **Author from scratch**.
4. Function name: `agri-send-approval-request`.
5. Runtime: `Python 3.12` (or current lab default).
6. Execution role: choose existing role with permissions.
7. Click **Create function**.
8. In **Configuration > Environment variables**, add:
   - `TABLE_NAME=agri-retrain-approvals`
   - `TOPIC_ARN=<SNS topic ARN>`
   - `APPROVAL_BASE_URL=<API Gateway invoke URL>`  
     Example: `https://abc123.execute-api.us-east-1.amazonaws.com/prod/decision`
9. In **Code** tab, paste this:

```python
import os
import json
import uuid
import time
import boto3

ddb = boto3.client("dynamodb")
sns = boto3.client("sns")

TABLE_NAME = os.environ["TABLE_NAME"]
TOPIC_ARN = os.environ["TOPIC_ARN"]
APPROVAL_BASE_URL = os.environ["APPROVAL_BASE_URL"]

def lambda_handler(event, context):
    token = str(uuid.uuid4())
    execution_arn = event["execution_arn"]

    ddb.put_item(
        TableName=TABLE_NAME,
        Item={
            "token": {"S": token},
            "execution_arn": {"S": execution_arn},
            "status": {"S": "PENDING"},
            "created_at": {"N": str(int(time.time()))}
        }
    )

    approve_url = f"{APPROVAL_BASE_URL}?token={token}&decision=approve"
    reject_url = f"{APPROVAL_BASE_URL}?token={token}&decision=reject"

    msg = (
        "Drift alarm triggered.\n\n"
        f"Execution: {execution_arn}\n\n"
        f"Approve retraining: {approve_url}\n"
        f"Reject retraining: {reject_url}\n"
    )

    sns.publish(
        TopicArn=TOPIC_ARN,
        Subject="Agri retraining approval required",
        Message=msg
    )

    return {"token": token}
```

10. Click **Deploy**.

---

## 4) Create Lambda: `agri-approval-decision`

Purpose:
- Receive admin decision from API Gateway.
- Update Step Functions callback (`SendTaskSuccess` / `SendTaskFailure`).

1. In **Lambda**, click **Create function**.
2. Name: `agri-approval-decision`.
3. Runtime: `Python`.
4. Role: same role (must allow DynamoDB + StepFunctions).
5. Click **Create function**.
6. Add environment variable:
   - `TABLE_NAME=agri-retrain-approvals`
7. Paste code:

```python
import os
import json
import boto3

ddb = boto3.client("dynamodb")
sfn = boto3.client("stepfunctions")
TABLE_NAME = os.environ["TABLE_NAME"]

def lambda_handler(event, context):
    qs = event.get("queryStringParameters") or {}
    token = qs.get("token")
    decision = (qs.get("decision") or "").lower()

    if not token or decision not in ("approve", "reject"):
        return {"statusCode": 400, "body": "Invalid token/decision"}

    resp = ddb.get_item(TableName=TABLE_NAME, Key={"token": {"S": token}})
    item = resp.get("Item")
    if not item:
        return {"statusCode": 404, "body": "Token not found"}

    task_token = item.get("task_token", {}).get("S")
    if not task_token:
        return {"statusCode": 409, "body": "Task token not ready"}

    if decision == "approve":
        sfn.send_task_success(taskToken=task_token, output=json.dumps({"approved": True}))
    else:
        sfn.send_task_failure(taskToken=task_token, error="Rejected", cause="Admin rejected retraining")

    ddb.update_item(
        TableName=TABLE_NAME,
        Key={"token": {"S": token}},
        UpdateExpression="SET #s = :s",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={":s": {"S": decision.upper()}}
    )

    return {"statusCode": 200, "body": f"Decision recorded: {decision}"}
```

8. Click **Deploy**.

---

## 5) Create Lambda: `agri-store-task-token`

Purpose:
- Save Step Functions callback task token in DynamoDB.

1. In **Lambda**, click **Create function**.
2. Name: `agri-store-task-token`.
3. Runtime: Python.
4. Add environment variable:
   - `TABLE_NAME=agri-retrain-approvals`
5. Paste code:

```python
import os
import boto3

ddb = boto3.client("dynamodb")
TABLE_NAME = os.environ["TABLE_NAME"]

def lambda_handler(event, context):
    token = event["token"]
    task_token = event["task_token"]

    ddb.update_item(
        TableName=TABLE_NAME,
        Key={"token": {"S": token}},
        UpdateExpression="SET task_token = :t",
        ExpressionAttributeValues={":t": {"S": task_token}}
    )
    return event
```

6. Click **Deploy**.

---

## 6) Create API Gateway Endpoint

1. Open **API Gateway**.
2. Click **Create API**.
3. Choose **HTTP API** (simplest).
4. Click **Build**.
5. Add integration: Lambda -> select `agri-approval-decision`.
6. Route:
   - Method: `GET`
   - Path: `/decision`
7. Stage name: `prod`.
8. Create API.
9. Copy **Invoke URL**.
10. Update Lambda `agri-send-approval-request` env var:
    - `APPROVAL_BASE_URL=<invoke-url>/decision`
11. Deploy/update Lambda.

---

## 7) Create Step Functions State Machine

1. Open **Step Functions**.
2. Click **Create state machine**.
3. Choose **Write workflow in code**.
4. Type: **Standard**.
5. Name: `agri-retrain-approval-workflow`.
6. Paste definition:

```json
{
  "Comment": "Human-in-the-loop approval before retraining",
  "StartAt": "AddExecutionArn",
  "States": {
    "AddExecutionArn": {
      "Type": "Pass",
      "Parameters": {
        "execution_arn.$": "$$.Execution.Id"
      },
      "ResultPath": "$.meta",
      "Next": "SendApprovalRequest"
    },
    "SendApprovalRequest": {
      "Type": "Task",
      "Resource": "arn:aws:states:::lambda:invoke",
      "Parameters": {
        "FunctionName": "agri-send-approval-request",
        "Payload": {
          "execution_arn.$": "$.meta.execution_arn"
        }
      },
      "ResultPath": "$.approval",
      "Next": "StoreTaskToken"
    },
    "StoreTaskToken": {
      "Type": "Task",
      "Resource": "arn:aws:states:::lambda:invoke.waitForTaskToken",
      "Parameters": {
        "FunctionName": "agri-store-task-token",
        "Payload": {
          "token.$": "$.approval.Payload.token",
          "task_token.$": "$$.Task.Token"
        }
      },
      "TimeoutSeconds": 86400,
      "ResultPath": "$.decision",
      "Next": "ApprovedChoice"
    },
    "ApprovedChoice": {
      "Type": "Choice",
      "Choices": [
        {
          "Variable": "$.decision.approved",
          "BooleanEquals": true,
          "Next": "StartRetraining"
        }
      ],
      "Default": "Rejected"
    },
    "StartRetraining": {
      "Type": "Task",
      "Resource": "arn:aws:states:::lambda:invoke",
      "Parameters": {
        "FunctionName": "agri-start-retraining",
        "Payload": {}
      },
      "End": true
    },
    "Rejected": {
      "Type": "Fail",
      "Error": "ApprovalRejected",
      "Cause": "Retraining rejected by admin"
    }
  }
}
```

7. Create/select execution role with permissions for Lambda invoke.
8. Click **Create state machine**.

---

## 8) IAM Permissions Checklist

Update the roles used by the three new Lambdas and Step Functions role.

Required actions:
- DynamoDB:
  - `dynamodb:GetItem`
  - `dynamodb:PutItem`
  - `dynamodb:UpdateItem`
- SNS:
  - `sns:Publish`
- Step Functions:
  - `states:SendTaskSuccess`
  - `states:SendTaskFailure`
- Lambda invoke (for Step Functions role):
  - `lambda:InvokeFunction`

Console path:
1. Open **IAM**.
2. Click **Roles**.
3. Open role.
4. Click **Add permissions** -> **Attach policies** or inline JSON policy.

---

## 9) Point EventBridge Alarm Rule to Step Functions

If you already have `agri-retrain-on-drift-rule`:
1. Open **EventBridge** -> **Rules**.
2. Click `agri-retrain-on-drift-rule`.
3. Click **Edit**.
4. In **Targets**, replace Lambda target (`agri-start-retraining`) with:
   - Target type: **Step Functions state machine**
   - Select `agri-retrain-approval-workflow`.
5. Save.

If creating new rule:
1. Create Event pattern rule.
2. Event source: `aws.cloudwatch`.
3. Detail type: `CloudWatch Alarm State Change`.
4. Pattern detail:
   - alarmName = `agri-overall-mape-alarm`
   - state.value = `ALARM`
5. Target = Step Functions state machine.

---

## 10) End-to-End Test

1. Trigger alarm to `ALARM` (test method you used previously).
2. Open **Step Functions** -> your state machine -> **Executions**.
3. Confirm execution started and is waiting at approval state.
4. Check admin email; open Approve link.
5. Refresh Step Functions execution:
   - should proceed to `StartRetraining`.
6. Open SageMaker Pipeline executions:
   - confirm new retraining execution started.

Reject test:
1. Trigger again.
2. Click Reject link.
3. Execution should end at `Rejected`.

---

## 11) Operational Notes

- Approval timeout currently `86400` seconds (24h); adjust if needed.
- Keep auto-retraining Lambda disabled as direct EventBridge target to avoid bypass.
- This runbook adds auditability: who approved and when is stored in DynamoDB + Step Functions history.

---

## 12) Rollback (Return to Fully Automatic Retraining)

1. EventBridge rule target -> switch back to `agri-start-retraining` Lambda.
2. Optionally disable:
   - Step Functions state machine
   - approval Lambdas
   - API Gateway endpoint
   - SNS topic/subscription

---

## 13) Human-in-the-Loop Architecture Visualization

```text
CloudWatch Alarm (agri-overall-mape-alarm)
  --> EventBridge Rule (agri-retrain-on-drift-rule)
  --> Step Functions (agri-retrain-approval-workflow)
  --> Lambda (agri-send-approval-request)
  --> SNS Topic (agri-retrain-approval-topic)
  --> Admin Email (Approve / Reject link)

Lambda (agri-send-approval-request)
  --> DynamoDB (agri-retrain-approvals) [store token]

Admin Email link click
  --> API Gateway (GET /decision)
  --> Lambda (agri-approval-decision)
  --> DynamoDB (agri-retrain-approvals) [update status]
  --> Step Functions callback (SendTaskSuccess / SendTaskFailure)
  --> Step Functions (resume workflow)

If Approved:
  Step Functions
    --> Lambda (agri-start-retraining)
    --> SageMaker Pipeline (agri-price-train-evaluate-register)
    --> Model Registry (new model version)

If Rejected or Timeout:
  Step Functions
    --> Stop (No retraining)
```

Notes:
- `Approved` path triggers retraining.
- `Rejected/Timeout` path exits safely.
- DynamoDB stores approval token and status for traceability.
