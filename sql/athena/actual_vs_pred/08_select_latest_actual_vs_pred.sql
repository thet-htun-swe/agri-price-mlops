-- Computes error metrics (MAPE) per run date; this is the KPI used for monitoring/alarm/retraining trigger.

SELECT *
FROM agri_mlops.agri_actual_vs_pred
ORDER BY date DESC
LIMIT 20;
