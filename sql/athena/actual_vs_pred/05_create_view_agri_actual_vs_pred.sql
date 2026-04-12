-- Joins actual and predicted rows by date, giving one unified comparison layer.\

CREATE OR REPLACE VIEW agri_mlops.agri_actual_vs_pred AS
SELECT
  a.date,
  a.target_next_day_price_coriander AS actual_coriander,
  p.target_next_day_price_coriander_pred AS pred_coriander,
  a.target_next_day_price_kale AS actual_kale,
  p.target_next_day_price_kale_pred AS pred_kale,
  a.target_next_day_price_lime AS actual_lime,
  p.target_next_day_price_lime_pred AS pred_lime,
  a.target_next_day_price_orange AS actual_orange,
  p.target_next_day_price_orange_pred AS pred_orange,
  a.target_next_day_price_red_chili AS actual_red_chili,
  p.target_next_day_price_red_chili_pred AS pred_red_chili,
  p.run_date
FROM agri_mlops.agri_features_actual a
JOIN agri_mlops.agri_predictions_curated p
  ON a.date = p.date;
