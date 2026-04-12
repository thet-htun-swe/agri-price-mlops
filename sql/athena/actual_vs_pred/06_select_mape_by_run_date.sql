-- After new prediction run folders arrive (run_date=...), refreshes partitions so Athena can query latest runs.

SELECT
  run_date,
  AVG(ABS((actual_coriander - pred_coriander) / NULLIF(actual_coriander, 0))) * 100 AS mape_coriander,
  AVG(ABS((actual_kale - pred_kale) / NULLIF(actual_kale, 0))) * 100 AS mape_kale,
  AVG(ABS((actual_lime - pred_lime) / NULLIF(actual_lime, 0))) * 100 AS mape_lime,
  AVG(ABS((actual_orange - pred_orange) / NULLIF(actual_orange, 0))) * 100 AS mape_orange,
  AVG(ABS((actual_red_chili - pred_red_chili) / NULLIF(actual_red_chili, 0))) * 100 AS mape_red_chili
FROM agri_mlops.agri_actual_vs_pred
GROUP BY run_date
ORDER BY run_date DESC;
