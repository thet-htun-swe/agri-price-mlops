const DATA_URL =
  "https://agri-price-dev-raw.s3.us-east-1.amazonaws.com/predictions/curated/latest/predictions.json";

function setStatus(text) {
  document.getElementById("status").textContent = text;
}

function asNumber(value) {
  if (value === null || value === undefined || value === "") return "-";
  const n = Number(value);
  if (Number.isNaN(n)) return "-";
  return n.toFixed(2);
}

function formatUtcTimestamp(raw) {
  if (!raw) return "-";
  const d = new Date(raw);
  if (Number.isNaN(d.getTime())) return String(raw);
  const localText = new Intl.DateTimeFormat(undefined, {
    year: "numeric",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
    timeZoneName: "short",
  }).format(d);
  return localText;
}

function renderSinglePrediction(row) {
  if (!row) {
    document.getElementById("predictionDateLabel").textContent =
      "Daily Predicted Prices";
    document.getElementById("corianderValue").textContent = "-";
    document.getElementById("kaleValue").textContent = "-";
    document.getElementById("limeValue").textContent = "-";
    document.getElementById("orangeValue").textContent = "-";
    document.getElementById("redChiliValue").textContent = "-";
    return;
  }

  document.getElementById("predictionDateLabel").textContent =
    `Daily Predicted Prices`;
  document.getElementById("corianderValue").textContent = asNumber(
    row.target_next_day_price_coriander_pred,
  );
  document.getElementById("kaleValue").textContent = asNumber(
    row.target_next_day_price_kale_pred,
  );
  document.getElementById("limeValue").textContent = asNumber(
    row.target_next_day_price_lime_pred,
  );
  document.getElementById("orangeValue").textContent = asNumber(
    row.target_next_day_price_orange_pred,
  );
  document.getElementById("redChiliValue").textContent = asNumber(
    row.target_next_day_price_red_chili_pred,
  );
}

async function loadPredictions() {
  try {
    setStatus("Loading");
    const resp = await fetch(DATA_URL, { cache: "no-store" });
    if (!resp.ok) {
      throw new Error(`HTTP ${resp.status}`);
    }

    const payload = await resp.json();

    document.getElementById("runDate").textContent = payload.run_date ?? "-";
    document.getElementById("generatedAt").textContent = formatUtcTimestamp(
      payload.generated_at_utc,
    );
    const rows = payload.data || [];
    renderSinglePrediction(rows.length > 0 ? rows[0] : null);
    setStatus("Ready");
  } catch (err) {
    setStatus("Error");
    document.getElementById("predictionDateLabel").textContent =
      "Daily Predicted Prices";
    document.getElementById("corianderValue").textContent = "Error";
    document.getElementById("kaleValue").textContent = "Error";
    document.getElementById("limeValue").textContent = "Error";
    document.getElementById("orangeValue").textContent = "Error";
    document.getElementById("redChiliValue").textContent = "Error";
  }
}

loadPredictions();
