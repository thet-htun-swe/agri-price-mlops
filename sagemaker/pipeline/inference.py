from __future__ import annotations

import io
import json
import pickle
from pathlib import Path

import pandas as pd


def model_fn(model_dir: str):
    with Path(model_dir, "model.pkl").open("rb") as file_obj:
        artifact = pickle.load(file_obj)
    return artifact


def input_fn(request_body: str, content_type: str):
    if content_type != "application/json":
        raise ValueError(f"Unsupported content type: {content_type}")
    payload = json.loads(request_body)
    if isinstance(payload, dict) and "instances" in payload:
        return pd.DataFrame(payload["instances"])
    if isinstance(payload, list):
        return pd.DataFrame(payload)
    if isinstance(payload, dict):
        return pd.DataFrame([payload])
    raise ValueError("Unsupported JSON payload shape.")


def predict_fn(input_data: pd.DataFrame, model_artifact):
    model = model_artifact["model"]
    feature_columns = model_artifact["feature_columns"]
    target_columns = model_artifact["target_columns"]
    predictions = model.predict(input_data[feature_columns])
    return pd.DataFrame(predictions, columns=target_columns)


def output_fn(prediction: pd.DataFrame, accept: str):
    if accept != "application/json":
        raise ValueError(f"Unsupported accept type: {accept}")
    return json.dumps({"predictions": prediction.to_dict(orient="records")})
