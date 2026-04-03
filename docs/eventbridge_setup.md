# EventBridge Daily Ingestion Setup

This note captures the exact manual setup used for the raw ingestion step.

## Goal

Run the price and weather Lambdas once per day through EventBridge.

## What must exist first

- One Lambda for price ingestion
- One Lambda for weather ingestion
- One EventBridge schedule rule for each Lambda
- One Lambda permission statement per rule

## Recommended schedule

- Price: `cron(0 1 * * ? *)`
- Weather: `cron(30 1 * * ? *)`

These times are only an example. Any daily schedule is fine for a term project.

## Create the EventBridge rule

1. Open `EventBridge`.
2. Go to `Rules`.
3. Choose `Create rule`.
4. Set `Rule type` to `Schedule`.
5. Enter a clear name, for example:
   - `agri-price-dev-ingest-prices-schedule`
   - `agri-price-dev-ingest-weather-schedule`
6. Enter the cron expression.
7. Add the Lambda as the target.
8. Save the rule.

## Add Lambda permission

Add one resource-based permission to each Lambda so EventBridge can invoke it.

Console fields:

- `Edit policy statement`: choose `AWS service`
- `Service`: `EventBridge (CloudWatch Events)`
- `Statement ID`: any unique name, for example `AllowEventBridgeInvokePrice`
- `Principal`: `events.amazonaws.com`
- `Source ARN`: the exact EventBridge rule ARN
- `Action`: `lambda:InvokeFunction`

The `Source ARN` must match the rule that will call the Lambda, for example:

`arn:aws:events:us-east-1:654654220088:rule/agri-price-dev-ingest-prices-schedule`

Use the weather rule ARN for the weather Lambda.

## Sequence to follow

1. Create the EventBridge rule.
2. Copy the rule ARN.
3. Add the Lambda permission using that rule ARN.
4. Verify the rule target points to the correct Lambda.
5. Wait for the next schedule or trigger a test run.
6. Confirm the Lambda ran and wrote a raw object to S3.

## Common mistakes

- Using the Lambda ARN instead of the EventBridge rule ARN
- Creating the rule target but forgetting the Lambda permission
- Reusing one permission statement for both Lambdas
- Choosing a schedule time without checking the time zone

## Verification checklist

- [ ] Price rule exists
- [ ] Weather rule exists
- [ ] Price Lambda has EventBridge invoke permission
- [ ] Weather Lambda has EventBridge invoke permission
- [ ] Rule target points to the intended Lambda
- [ ] A scheduled run creates a new raw object in S3
- [ ] CloudWatch logs show the invocation
