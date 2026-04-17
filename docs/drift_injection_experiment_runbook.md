# Drift Injection Experiment Runbook

This runbook shows how to run a **safe drift-detection experiment** by injecting fake actual values in Athena views (not by modifying production S3 files).

Goal:

1. Simulate sudden performance degradation.
2. Verify monitoring chain: Athena -> Monitor Lambda -> CloudWatch Alarm -> EventBridge -> (Human approval / Retraining).
3. Roll back cleanly.

---

## 0) Safety Rules

Follow these rules for this experiment:

1. Do **not** overwrite production parquet files in S3.
2. Use separate Athena **test views** only.
3. Revert monitor Lambda SQL after test.

---

## 1) Prerequisites

Confirm these are ready:

1. Curated predictions available in `s3://agri-price-dev-raw/predictions/curated/run_date=.../`.
2. Athena database and views already created (from your monitoring setup).
3. `lambda_model_monitor` exists and publishes `OverallMAPE`.
4. CloudWatch alarm `agri-overall-mape-alarm` exists.
5. EventBridge rule for retraining trigger exists.

---

## 2) Choose a Test Run Date

1. Open **Athena**.
2. Select your database (example: `agri_mlops`).
3. Run:

```sql
SELECT DISTINCT run_date
FROM agri_actual_vs_pred
ORDER BY run_date DESC
LIMIT 10;
```

4. Pick one recent run date, example: `2026-04-12`.

---

## 3) Validate a Good Run Date (Non-Null Actuals)

Before injecting drift, confirm your chosen `run_date` has usable actual values.

Run this in Athena:

```sql
SELECT
  run_date,
  date,
  actual_coriander,
  actual_kale,
  actual_lime,
  actual_orange,
  actual_red_chili
FROM agri_actual_vs_pred
WHERE actual_coriander IS NOT NULL
  AND actual_kale IS NOT NULL
  AND actual_lime IS NOT NULL
  AND actual_orange IS NOT NULL
  AND actual_red_chili IS NOT NULL
  AND actual_coriander <> 0
  AND actual_kale <> 0
  AND actual_lime <> 0
  AND actual_orange <> 0
  AND actual_red_chili <> 0
ORDER BY run_date DESC, date DESC
LIMIT 20;
```

Pick one run date from results (example: `2026-04-12`).

---

## 4) Create Injected Comparison View

Create an injected copy directly from `agri_actual_vs_pred` and distort only one `run_date`.

1. Replace `2026-04-12` with your selected run date.
2. Start with multiplier `5.0`. If needed, increase to `10.0`.

```sql
CREATE OR REPLACE VIEW agri_actual_vs_pred_injected AS
SELECT
  date,
  CASE WHEN run_date = '2026-04-12' THEN actual_coriander * 5.0 ELSE actual_coriander END AS actual_coriander,
  pred_coriander,
  CASE WHEN run_date = '2026-04-12' THEN actual_kale * 5.0 ELSE actual_kale END AS actual_kale,
  pred_kale,
  CASE WHEN run_date = '2026-04-12' THEN actual_lime * 5.0 ELSE actual_lime END AS actual_lime,
  pred_lime,
  CASE WHEN run_date = '2026-04-12' THEN actual_orange * 5.0 ELSE actual_orange END AS actual_orange,
  pred_orange,
  CASE WHEN run_date = '2026-04-12' THEN actual_red_chili * 5.0 ELSE actual_red_chili END AS actual_red_chili,
  pred_red_chili,
  run_date
FROM agri_actual_vs_pred;
```

---

## 5) Verify MAPE Spike in Athena (Before Touching Lambda)

1. Run baseline (production view):

```sql
SELECT
  run_date,
  AVG(ABS((actual_coriander - pred_coriander) / NULLIF(actual_coriander, 0))) * 100 AS mape_coriander,
  AVG(ABS((actual_kale - pred_kale) / NULLIF(actual_kale, 0))) * 100 AS mape_kale,
  AVG(ABS((actual_lime - pred_lime) / NULLIF(actual_lime, 0))) * 100 AS mape_lime,
  AVG(ABS((actual_orange - pred_orange) / NULLIF(actual_orange, 0))) * 100 AS mape_orange,
  AVG(ABS((actual_red_chili - pred_red_chili) / NULLIF(actual_red_chili, 0))) * 100 AS mape_red_chili
FROM agri_actual_vs_pred
WHERE run_date = '2026-04-12'
GROUP BY run_date;
```

2. Run injected version:

```sql
SELECT
  run_date,
  AVG(ABS((actual_coriander - pred_coriander) / NULLIF(actual_coriander, 0))) * 100 AS mape_coriander,
  AVG(ABS((actual_kale - pred_kale) / NULLIF(actual_kale, 0))) * 100 AS mape_kale,
  AVG(ABS((actual_lime - pred_lime) / NULLIF(actual_lime, 0))) * 100 AS mape_lime,
  AVG(ABS((actual_orange - pred_orange) / NULLIF(actual_orange, 0))) * 100 AS mape_orange,
  AVG(ABS((actual_red_chili - pred_red_chili) / NULLIF(actual_red_chili, 0))) * 100 AS mape_red_chili
FROM agri_actual_vs_pred_injected
WHERE run_date = '2026-04-12'
GROUP BY run_date;
```

3. Confirm injected MAPE is significantly higher.
4. If still low, increase multiplier in section 4 and rerun.

---

## 6) Temporarily Point Monitor Lambda to Injected View

### Option A (recommended): temporary code edit in Lambda console

1. Open **Lambda** -> `lambda_model_monitor`.
2. In **Code** tab, update SQL string:
   - change `FROM agri_actual_vs_pred`
   - to `FROM agri_actual_vs_pred_injected`
3. update the run date

```sql
SELECT
  AVG(ABS((actual_coriander - pred_coriander) / NULLIF(actual_coriander, 0))) * 100 AS mape_coriander,
  AVG(ABS((actual_kale - pred_kale) / NULLIF(actual_kale, 0))) * 100 AS mape_kale,
  AVG(ABS((actual_lime - pred_lime) / NULLIF(actual_lime, 0))) * 100 AS mape_lime,
  AVG(ABS((actual_orange - pred_orange) / NULLIF(actual_orange, 0))) * 100 AS mape_orange,
  AVG(ABS((actual_red_chili - pred_red_chili) / NULLIF(actual_red_chili, 0))) * 100 AS mape_red_chili
FROM agri_actual_vs_pred_injected
WHERE run_date = '2026-04-12';
```

4. Click **Deploy**.

### Option B: if your code supports env var SQL (skip if not implemented)

1. Set env var with injected query.
2. Save and deploy.

---

## 7) Trigger Monitoring and Observe Alarm Chain

1. In `lambda_model_monitor`, open **Test** tab.
2. Run a test event (empty `{}` is fine if your handler does not require input).
3. Check response:
   - `status = published`
   - `overall_mape` should be high.

4. Open **CloudWatch** -> **Metrics**:
   - Namespace: your monitor namespace (example `AgriPriceML`)
   - Metric: `OverallMAPE`
   - Confirm spike point appears.

5. Open **CloudWatch** -> **Alarms**:
   - Check `agri-overall-mape-alarm` state.
   - Should move to `In alarm` (depending on evaluation settings).

6. Open **EventBridge** rule monitoring tab:
   - Verify `MatchedEvents` / `Invocations` increment.

7. If you use human-in-loop:
   - Open **Step Functions** executions.
   - Verify new execution started and approval email was sent.

---

## 8) Capture Evidence for Proposal

Collect screenshots / outputs:

1. Athena baseline vs injected MAPE query results.
2. CloudWatch metric spike.
3. CloudWatch alarm state change to `In alarm`.
4. EventBridge matched event/invocation count.
5. Step Functions execution (waiting approval / approved / rejected).
6. (Optional) SageMaker pipeline execution started after approval.

---

## 9) Rollback to Production

1. Revert `lambda_model_monitor` SQL:
   - back to `FROM agri_actual_vs_pred`.
2. Deploy Lambda.
3. Drop test views in Athena:

```sql
DROP VIEW IF EXISTS agri_actual_vs_pred_injected;
DROP VIEW IF EXISTS agri_features_actual_injected;
```

4. Run monitor Lambda once more.
5. Confirm metric returns to normal pattern.

---

## 10) Troubleshooting

### A) Alarm not triggered

1. Check alarm threshold/evaluation periods.
2. Confirm injected run_date is the latest run_date if your SQL uses `MAX(run_date)`.
3. Verify monitor Lambda published metric successfully.
4. Athena accepts one statement per run in this UI; run each query separately.

### B) Lambda publishes but no EventBridge trigger

1. Verify alarm actually entered `ALARM` state.
2. Check EventBridge rule event pattern matches alarm name and state.

### C) No Step Functions execution

1. Confirm EventBridge target points to correct state machine.
2. Check IAM permission for EventBridge to start state machine.

---

## 11) Simple Architecture (Text)

```text
Athena test view (injected actuals)
  --> lambda_model_monitor (temporary SQL points to injected view)
  --> CloudWatch OverallMAPE metric (spike)
  --> CloudWatch alarm: agri-overall-mape-alarm = ALARM
  --> EventBridge rule
  --> Step Functions (human approval flow)
  --> (if approved) agri-start-retraining Lambda
  --> SageMaker train/evaluate/register pipeline
```
