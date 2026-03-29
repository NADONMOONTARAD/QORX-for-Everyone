"""AI-related small helpers: confidence threshold and decision helpers."""

import re
from datetime import date, datetime
from typing import Any

from .unit_handling import scale_value_by_unit


_DATE_FORMATS = (
    "%Y-%m-%d",
    "%Y/%m/%d",
    "%m/%d/%Y",
    "%b %d, %Y",
    "%B %d, %Y",
)


def should_upsert_ai_entry(confidence: float, threshold: float) -> bool:
    try:
        return float(confidence) >= float(threshold)
    except Exception:
        return False


def _coerce_year_value(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        year = int(value)
        if 1900 <= year <= 2100:
            return year
        return None
    s = str(value).strip()
    if not s:
        return None
    match = re.search(r"(19|20)\d{2}", s)
    if match:
        year = int(match.group(0))
        if 1900 <= year <= 2100:
            return year
    return None


def _extract_report_year(entry: dict) -> int | None:
    for candidate in (
        entry.get("year"),
        entry.get("fiscal_year"),
        entry.get("year_reported"),
    ):
        year = _coerce_year_value(candidate)
        if year is not None:
            return year
    return None


def _coerce_report_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    s = str(value).strip()
    if not s:
        return None
    try:
        return datetime.fromisoformat(s).date()
    except ValueError:
        pass
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _normalize_ai_segment_entry(
    entry: dict,
    confidence_threshold: float,
    name_keys: tuple[str, ...],
) -> dict | None:
    if not isinstance(entry, dict):
        return None
    conf = entry.get("confidence")
    if conf is None:
        conf = entry.get("ai_confidence")
    try:
        conf = float(conf or 0.0)
    except Exception:
        conf = 0.0
    if conf < float(confidence_threshold):
        return None

    name = None
    for key in name_keys:
        candidate = entry.get(key)
        if candidate:
            candidate_str = str(candidate).strip()
            if candidate_str:
                name = candidate_str
                break
    if not name:
        return None

    value_obj = entry.get("value")
    unit = entry.get("unit")
    numeric_value = None
    if isinstance(value_obj, dict):
        numeric_value = value_obj.get("value")
        unit = value_obj.get("unit") or unit
    elif value_obj is not None:
        numeric_value = value_obj

    if numeric_value is None:
        amount_obj = entry.get("amount")
        if isinstance(amount_obj, dict):
            numeric_value = amount_obj.get("value")
            unit = amount_obj.get("unit") or unit
        elif amount_obj is not None:
            numeric_value = amount_obj

    if numeric_value is None:
        numeric_value = entry.get("revenue_amount_raw") or entry.get("revenue_amount")
        unit = entry.get("revenue_unit") or unit

    raw_numeric, scaled_value = scale_value_by_unit(numeric_value, unit)
    if scaled_value is None and raw_numeric is not None:
        try:
            scaled_value = int(round(float(raw_numeric)))
        except Exception:
            scaled_value = None

    report_date = _coerce_report_date(entry.get("report_date"))
    report_year = _extract_report_year(entry)
    if report_date is not None and report_year is None:
        report_year = report_date.year

    growth = (
        entry.get("revenue_growth_pct")
        or entry.get("growth_pct")
        or entry.get("growth_percent")
        or entry.get("growth")
    )

    return {
        "segment_original_name": name,
        "segment_group": entry.get("segment_group"),
        "revenue_amount_raw": raw_numeric,
        "revenue_amount": scaled_value,
        "revenue_unit": (entry.get("revenue_unit") or unit) or None,
        "revenue_growth_pct": growth,
        "data_source": entry.get("data_source") or "Gemini",
        "confidence": conf,
        "ai_confidence": conf,
        "report_year": report_year,
        "report_date": report_date,
    }


def normalize_ai_geo_entry(entry: dict, confidence_threshold: float) -> dict | None:
    """Normalize an AI-provided geographic entry into the DB payload."""
    normalized = _normalize_ai_segment_entry(
        entry,
        confidence_threshold,
        ("region", "segment_original_name", "name"),
    )
    return normalized


def normalize_ai_product_entry(entry: dict, confidence_threshold: float) -> dict | None:
    """Normalize an AI-provided product/operating segment entry."""
    return _normalize_ai_segment_entry(
        entry,
        confidence_threshold,
        ("segment", "segment_original_name", "name", "product"),
    )
