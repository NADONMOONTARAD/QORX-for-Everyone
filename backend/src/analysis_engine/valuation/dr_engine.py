"""Public-edition discount-rate and aggregation helpers.

This repo intentionally keeps valuation aggregation plain and reviewable by
using standard educational heuristics in public. Fuller thesis-specific tuning
is maintained separately and can be reviewed on request.
"""

import pandas as pd
from typing import List, Dict, Any

DEFAULT_WEIGHT_QUANT = 0.7

EXTERNAL_RISK_PENALTIES: Dict[str, float] = {
    "REGULATORY_UNPREDICTABLE": 0.015,
    "GEOPOLITICAL_RISK": 0.01,
    "SANCTION_RISK": 0.01,
    "CURRENCY_CONTROLS": 0.008,
    "CAPITAL_CONTROLS": 0.008,
}

EXTERNAL_RISK_LABELS: Dict[str, str] = {
    "REGULATORY_UNPREDICTABLE": "Unpredictable Regulatory Risk",
    "GEOPOLITICAL_RISK": "Geopolitical Risk",
    "SANCTION_RISK": "Sanction Risk",
    "CURRENCY_CONTROLS": "Currency Controls",
    "CAPITAL_CONTROLS": "Capital Controls",
}


def _get_insider_scoring_thresholds(self) -> tuple[float, float]:
    """
    Return the insider ownership thresholds for scoring 10/20 and 20/20 points
    based on business stage / market cap.

    Returns a tuple (half_threshold_pct, full_threshold_pct), both in percent terms.

    Mapping (from user spec):
    - Early-stage: 5% -> 10/20, 25% -> 20/20
    - Turnaround: 3% -> 10/20, 20% -> 20/20
    - Mega Cap > 200B: 1% -> 10/20, 10% -> 20/20
    - Mid Cap 10–200B: 3% -> 10/20, 20% -> 20/20
    - Small Cap < 10B: 10% -> 10/20, 50% -> 20/20
    """
    company_type, _ = self._get_confident_value("company_type", 0)
    company_type = (company_type or "").strip()
    market_cap = (self.profile or {}).get("market_cap", 0) or 0

    if company_type == "Early-stage":
        return (5.0, 25.0)
    if company_type == "Turnaround":
        return (3.0, 20.0)

    if market_cap > 200e9:
        return (1.0, 10.0)
    if market_cap > 10e9:
        return (3.0, 20.0)
    return (10.0, 50.0)


def _calculate_qual_adjustment(
    self, moat_score: float
) -> tuple[float, List[Dict[str, Any]]]:
    """
    Maintain backwards compatibility signature but focus exclusively on
    external / uncontrollable risk sources. Internal qualitative signals are
    handled inside the conviction engine.

    Returns:
        Tuple[float, list]: (Total Adjustment, List of reasons for adjustment)
    """
    risk_adj = 0.0
    breakdown: List[Dict[str, Any]] = []

    risk_tags, _ = self._get_confident_value("business_risk_tags")
    risk_tags = [str(tag).upper() for tag in (risk_tags or [])]

    for tag in risk_tags:
        delta = EXTERNAL_RISK_PENALTIES.get(tag, 0.0)
        if delta:
            description = EXTERNAL_RISK_LABELS.get(tag, tag.replace("_", " ").title())
            breakdown.append(
                {
                    "code": tag,
                    "label": description,
                    "delta": float(delta),
                    "type": "external_risk",
                }
            )
            risk_adj += delta

    risk_adj = max(0.0, risk_adj)
    return risk_adj, breakdown


def get_dynamic_threshold(self, weight_quant: float) -> float:
    """
    Retained for compatibility with older callers.

    The public edition no longer varies this threshold by company size.
    """
    _ = self, weight_quant
    return 0.5


def robust_metric(
    self, series: pd.Series, weight_quant: float, window: int | None = None
) -> float | None:
    """
    Public-edition aggregation rule.

    Keep the signature for compatibility, but use a plain median of the most
    recent values instead of a tuned outlier model.
    """
    _ = self, weight_quant
    cleaned = series.dropna().astype(float)
    if window is not None and window > 0:
        cleaned = cleaned.tail(window)

    if cleaned.empty:
        return None

    return float(cleaned.median())


def _build_discount_rate_explanation(
    base_rate: float, adjustments: List[Dict[str, Any]], final_rate: float
) -> str:
    if not adjustments:
        return (
            f"Starting from base discount rate {base_rate:.2%} with no special additions, "
            f"thus using discount rate {final_rate:.2%}."
        )

    pieces = []
    for item in adjustments:
        label = item.get("label") or item.get("code") or "Adjustment"
        delta = float(item.get("delta", 0.0))
        pieces.append(f"{label} +{delta:.2%}")

    joined = ", ".join(pieces)
    return (
        f"Starting from base discount rate {base_rate:.2%}, then increased due to {joined}, "
        f"resulting in final discount rate {final_rate:.2%}."
    )


def _update_discount_rate_insight(
    analyzer,
    *,
    base_rate: float,
    final_rate: float,
    adjustments: List[Dict[str, Any]],
) -> None:
    checklist = getattr(analyzer, "checklist_results", None)
    if not isinstance(checklist, dict):
        return

    valuation_insights = checklist.setdefault("valuation_insights", {})
    valuation_insights["discount_rate"] = {
        "base_rate": float(base_rate),
        "final_rate": float(final_rate),
        "adjustments": adjustments,
        "explanation": _build_discount_rate_explanation(
            base_rate, adjustments, final_rate
        ),
    }


def _calculate_dynamic_discount_rate(
    self, moat_score: float, quant_adj: float
) -> float:
    print("--- [DR Engine] Calculating Full Dynamic Discount Rate ---")
    base_DR = 0.10
    print(f"    Base Discount Rate (minimum): {base_DR:.2%}")

    external_adj, external_breakdown = _calculate_qual_adjustment(self, moat_score)
    external_adj = max(0.0, external_adj)
    print(f"    External Risk Adjustment: {external_adj:.2%}")

    adjusted_DR = base_DR + external_adj
    print(f"    Adjusted Discount Rate (pre-floor): {adjusted_DR:.2%}")

    final_DR = max(base_DR, adjusted_DR)
    print(f"--- [DR Engine] Final Calculated DR: {final_DR:.2%} ---")

    adjustments_payload = [dict(item) for item in external_breakdown]
    _update_discount_rate_insight(
        self,
        base_rate=base_DR,
        final_rate=final_DR,
        adjustments=adjustments_payload,
    )

    return final_DR
