import os
import time
import boto3

REGION = os.environ.get("AWS_REGION", "us-east-1")
athena = boto3.client("athena", region_name=REGION)
cloudwatch = boto3.client("cloudwatch", region_name=REGION)

SQL = """
SELECT
  AVG(ABS((actual_coriander - pred_coriander) / NULLIF(actual_coriander, 0))) * 100 AS mape_coriander,
  AVG(ABS((actual_kale - pred_kale) / NULLIF(actual_kale, 0))) * 100 AS mape_kale,
  AVG(ABS((actual_lime - pred_lime) / NULLIF(actual_lime, 0))) * 100 AS mape_lime,
  AVG(ABS((actual_orange - pred_orange) / NULLIF(actual_orange, 0))) * 100 AS mape_orange,
  AVG(ABS((actual_red_chili - pred_red_chili) / NULLIF(actual_red_chili, 0))) * 100 AS mape_red_chili
FROM agri_actual_vs_pred
WHERE run_date = (SELECT MAX(run_date) FROM agri_actual_vs_pred)
"""
REPAIR_QUERIES = (
    "MSCK REPAIR TABLE agri_predictions_curated",
    "MSCK REPAIR TABLE agri_features_actual",
)

def _to_float(v):
    return float(v) if v not in (None, "") else None

def _wait_for_query(query_execution_id, poll_seconds=2, timeout_seconds=120):
    start = time.time()
    while True:
        query = athena.get_query_execution(QueryExecutionId=query_execution_id)["QueryExecution"]
        status = query["Status"]["State"]
        if status in ("SUCCEEDED", "FAILED", "CANCELLED"):
            return query
        if time.time() - start > timeout_seconds:
            raise TimeoutError(
                f"Athena query timed out after {timeout_seconds}s: {query_execution_id}"
            )
        time.sleep(poll_seconds)


def _execute_query_and_wait(*, query_string, database, output_s3, workgroup, poll_seconds, timeout_seconds):
    start = athena.start_query_execution(
        QueryString=query_string,
        QueryExecutionContext={"Database": database},
        ResultConfiguration={"OutputLocation": output_s3},
        WorkGroup=workgroup,
    )
    query_execution_id = start["QueryExecutionId"]
    query = _wait_for_query(
        query_execution_id=query_execution_id,
        poll_seconds=poll_seconds,
        timeout_seconds=timeout_seconds,
    )
    status = query["Status"]["State"]
    if status != "SUCCEEDED":
        reason = query["Status"].get("StateChangeReason", "Unknown Athena failure reason")
        raise RuntimeError(
            f"Athena query failed. status={status}, reason={reason}, query_execution_id={query_execution_id}"
        )
    return query_execution_id

def lambda_handler(event, context):
    database = os.environ["ATHENA_DATABASE"]
    output_s3 = os.environ["ATHENA_OUTPUT_S3"]
    namespace = os.environ["CLOUDWATCH_NAMESPACE"]
    model_group = os.environ["MODEL_PACKAGE_GROUP"]
    workgroup = os.environ.get("ATHENA_WORKGROUP", "primary")
    poll_seconds = int(os.environ.get("ATHENA_POLL_SECONDS", "2"))
    timeout_seconds = int(os.environ.get("ATHENA_TIMEOUT_SECONDS", "120"))

    repair_query_ids = []
    for repair_sql in REPAIR_QUERIES:
        repair_qid = _execute_query_and_wait(
            query_string=repair_sql,
            database=database,
            output_s3=output_s3,
            workgroup=workgroup,
            poll_seconds=poll_seconds,
            timeout_seconds=timeout_seconds,
        )
        repair_query_ids.append(repair_qid)

    qid = _execute_query_and_wait(
        query_string=SQL,
        database=database,
        output_s3=output_s3,
        workgroup=workgroup,
        poll_seconds=poll_seconds,
        timeout_seconds=timeout_seconds,
    )

    rows = athena.get_query_results(QueryExecutionId=qid)["ResultSet"]["Rows"]
    if len(rows) < 2:
        return {
            "status": "skipped",
            "reason": "No Athena result row found.",
            "query_execution_id": qid,
        }

    vals = [c.get("VarCharValue", "") for c in rows[1]["Data"]]
    mapes = [_to_float(v) for v in vals]
    mapes = [m for m in mapes if m is not None]

    if not mapes:
        return {
            "status": "skipped",
            "reason": "MAPE values are empty (likely no labeled actuals yet).",
            "query_execution_id": qid,
        }

    overall_mape = sum(mapes) / len(mapes)

    cloudwatch.put_metric_data(
        Namespace=namespace,
        MetricData=[{
            "MetricName": "OverallMAPE",
            "Dimensions": [{"Name": "ModelPackageGroup", "Value": model_group}],
            "Value": overall_mape,
            "Unit": "None",
        }],
    )

    return {
        "status": "published",
        "overall_mape": overall_mape,
        "query_execution_id": qid,
        "repair_query_execution_ids": repair_query_ids,
        "region": REGION,
        "workgroup": workgroup,
    }
