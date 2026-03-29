from typing import Any, Tuple
import pandas as pd


def get_confident_value(
    qual_summary: dict, key: str, penalty_if_missing: float = 0.005
) -> Tuple[Any, float]:
    """Return (value, penalty) with the same heuristic as original _get_confident_value.

    Expects qual_summary entries to be dicts with 'value' and optional 'confidence'.
    """
    data_point = qual_summary.get(key)
    if not data_point or "value" not in data_point:
        return None, penalty_if_missing

    value = data_point["value"]
    confidence = data_point.get("confidence", 0.0)

    if confidence >= 0.7:
        return value, 0.0
    elif confidence >= 0.5:
        return value, penalty_if_missing / 2
    else:
        return None, penalty_if_missing


def check_latest_metric(
    latest_row: pd.Series, metric: str, condition: str, target: float
) -> dict:
    """Helper that mirrors _check: evaluate 'value <op> target' safely for the latest row."""
    value = latest_row.get(metric)

    if value is None or pd.isna(value):
        return {"pass": None, "value": "N/A", "note": "Metric not available"}

    try:
        passed = eval(f"value {condition} target")
        return {"pass": bool(passed), "value": float(round(value, 4))}
    except Exception:
        return {"pass": False, "value": float(value), "note": "Evaluation error"}
