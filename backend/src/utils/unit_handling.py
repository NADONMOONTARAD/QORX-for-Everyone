"""Helpers for handling numeric value units coming from AI or scrapers.

Provides a single function `scale_value_by_unit` which returns both the raw
value and the scaled (int) value in base units (USD). It supports 'million'
and 'billion' keywords (case-insensitive, substring match).
"""

from typing import Tuple, Optional


def scale_value_by_unit(
    value: float | int | None, unit: str | None
) -> Tuple[Optional[float], Optional[int]]:
    """Return (raw_value, scaled_int) where scaled_int is value scaled to units (no fractional)

    Rules:
    - If unit contains 'million' -> multiply by 1_000_000
    - If unit contains 'billion' -> multiply by 1_000_000_000
    - Otherwise, if unit contains 'k' or 'thousand' multiply by 1_000
    - If value is None -> return (None, None)
    - scaled_int returns int() if possible, else None
    """
    if value is None:
        return None, None
    try:
        v = float(value)
    except Exception:
        return None, None

    u = (unit or "").lower()
    scale = 1
    if "billion" in u:
        scale = 1_000_000_000
    elif "million" in u:
        scale = 1_000_000
    elif "thousand" in u or (u == "k"):
        scale = 1_000

    scaled = v * scale
    try:
        return v, int(round(scaled))
    except Exception:
        return v, None
