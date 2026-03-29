# backend/src/analysis_engine/checklist/conviction.py

from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

import pandas as pd

from backend.src.analysis_engine.valuation.dr_engine import DEFAULT_WEIGHT_QUANT


@dataclass
class ScoreBlock:
    name: str
    points: float
    max_points: float
    components: Dict[str, Any]

    @property
    def ratio(self) -> float:
        if self.max_points <= 0:
            return 0.0
        return max(0.0, min(1.0, float(self.points) / float(self.max_points)))


def _safe_series_metric(
    analyzer, column: str, weight_quant: float, window: int | None = None
) -> Optional[float]:
    """Compute a robust metric over available series."""

    annual_only = {
        "roe",
        "roic",
        "gross_margin",
        "net_profit_margin",
        "interest_coverage",
        "payout_ratio",
        "affo_yield",
        "combined_ratio",
        "operating_margin",
    }

    qdf = getattr(analyzer, "quant_df", None)
    try:
        if qdf is not None and not qdf.empty:
            source = qdf
            if column in annual_only and "period_type" in qdf.columns:
                annual_rows = qdf[qdf["period_type"] == "A"]
                if not annual_rows.empty:
                    source = annual_rows
            series = pd.to_numeric(source.get(column, pd.Series()), errors="coerce")
        else:
            series = pd.to_numeric(pd.Series(), errors="coerce")
    except Exception:
        try:
            series = pd.to_numeric(
                getattr(analyzer, "quant_df", pd.Series()).get(column, pd.Series()),
                errors="coerce",
            )
        except Exception:
            series = pd.Series()

    try:
        value = analyzer.robust_metric(series, weight_quant, window)
        if value is None or pd.isna(value):
            return None
        return float(value)
    except Exception:
        return None


def _fetch_confident_value(analyzer, key: str) -> Any:
    try:
        value, _ = analyzer._get_confident_value(key, 0.0)
        return value
    except Exception:
        return None


def _extract_signal_text(value: Any) -> str:
    if isinstance(value, dict):
        for key in ("value", "rating", "label", "notes", "evidence", "rationale"):
            nested = value.get(key)
            if isinstance(nested, str) and nested.strip():
                return nested.strip()
        return ""
    if isinstance(value, str):
        return value.strip()
    return ""


def _normalize_signal_level(value: Any) -> str:
    return _extract_signal_text(value).strip().lower()


def _get_recent_annual_series(analyzer, column: str, lookback: int = 5) -> pd.Series:
    qdf = getattr(analyzer, "quant_df", None)
    if qdf is None or qdf.empty or column not in qdf.columns:
        return pd.Series(dtype=float)

    try:
        annuals = qdf
        if "period_type" in qdf.columns:
            annuals = qdf[qdf["period_type"] == "A"]
        if annuals.empty:
            return pd.Series(dtype=float)
        annuals = annuals.sort_values("report_date").tail(lookback)
        return pd.to_numeric(annuals.get(column), errors="coerce").dropna()
    except Exception:
        return pd.Series(dtype=float)


def _build_public_score_block(
    name: str, points: float, max_points: float, components: Dict[str, Any]
) -> ScoreBlock:
    return ScoreBlock(
        name=name,
        points=max(0.0, min(float(max_points), float(points))),
        max_points=float(max_points),
        components=components,
    )


def calculate_moat_score(analyzer) -> Tuple[float, str]:
    """Public GitHub edition moat score using a broad, transparent rubric."""

    qual_summary = getattr(analyzer, "qual_summary", {}) or {}
    identified_moats = qual_summary.get("moats_identified", [])
    if not isinstance(identified_moats, list):
        identified_moats = []

    strong_count = 0
    moderate_count = 0
    for moat in identified_moats:
        if not isinstance(moat, dict):
            continue
        strength = str(moat.get("strength") or "").strip().lower()
        if strength in {"strong", "high"}:
            strong_count += 1
        elif strength in {"moderate", "medium"}:
            moderate_count += 1

    final_score = min(5.0, strong_count * 1.75 + moderate_count * 0.75)

    if final_score >= 3.5:
        moat_rating = "Wide Durable Moat"
    elif final_score >= 2.0:
        moat_rating = "Strong Moat"
    elif final_score > 0:
        moat_rating = "Narrow Moat"
    else:
        moat_rating = "No Moat"

    return float(final_score), moat_rating


def calculate_conviction_score(
    analyzer, moat_score: float, margin_of_safety: float, final_dr: float
) -> float:
    """Public GitHub edition conviction score with a broad educational rubric."""

    sector = str((getattr(analyzer, "profile", {}) or {}).get("sector") or "").strip().upper()
    is_financial = sector == "FINANCIAL SERVICES"

    revenue_growth = _safe_series_metric(analyzer, "revenue_growth", DEFAULT_WEIGHT_QUANT, 5)
    positive_growth_periods = int(
        (_get_recent_annual_series(analyzer, "revenue_growth", 5) > 0).sum()
    )

    growth_points = 0.0
    growth_components: Dict[str, Any] = {}

    if revenue_growth is not None and revenue_growth >= 0.10:
        magnitude_points = 8.0
    elif revenue_growth is not None and revenue_growth >= 0.03:
        magnitude_points = 5.0
    elif revenue_growth is not None and revenue_growth > 0:
        magnitude_points = 2.0
    else:
        magnitude_points = 0.0
    growth_components["growth_magnitude"] = {
        "value": revenue_growth,
        "threshold": 0.03,
        "points": magnitude_points,
        "max_points": 8.0,
        "note": "Broad public-edition revenue growth check",
    }
    growth_points += magnitude_points

    if positive_growth_periods >= 4:
        consistency_points = 6.0
    elif positive_growth_periods >= 2:
        consistency_points = 3.0
    else:
        consistency_points = 0.0
    growth_components["growth_consistency"] = {
        "value": positive_growth_periods,
        "total_periods": 5,
        "points": consistency_points,
        "max_points": 6.0,
        "note": "Count of positive annual revenue-growth periods in recent history",
    }
    growth_points += consistency_points
    growth_block = _build_public_score_block("growth", growth_points, 14.0, growth_components)

    return_metric_name = "roe" if is_financial else "roic"
    return_metric_key = "roe_gte_12pct" if is_financial else "roic_gte_15pct"
    return_metric_value = _safe_series_metric(
        analyzer, return_metric_name, DEFAULT_WEIGHT_QUANT, 5
    )
    net_margin = _safe_series_metric(analyzer, "net_profit_margin", DEFAULT_WEIGHT_QUANT, 5)

    profitability_points = 0.0
    profitability_components: Dict[str, Any] = {}

    if return_metric_value is not None and return_metric_value >= (0.12 if is_financial else 0.15):
        return_points = 10.0
    elif return_metric_value is not None and return_metric_value >= 0.08:
        return_points = 6.0
    else:
        return_points = 0.0
    profitability_components[return_metric_key] = {
        "value": return_metric_value,
        "threshold": 0.12 if is_financial else 0.15,
        "points": return_points,
        "max_points": 10.0,
        "note": "Broad public-edition return metric",
    }
    profitability_points += return_points

    if net_margin is not None and net_margin >= 0.10:
        net_margin_points = 6.0
    elif net_margin is not None and net_margin >= 0.03:
        net_margin_points = 3.0
    else:
        net_margin_points = 0.0
    profitability_components["net_margin_gte_10pct"] = {
        "value": net_margin,
        "threshold": 0.10,
        "points": net_margin_points,
        "max_points": 6.0,
        "note": "Broad public-edition net margin check",
    }
    profitability_points += net_margin_points
    profitability_block = _build_public_score_block(
        "profitability_quality",
        profitability_points,
        16.0,
        profitability_components,
    )

    debt_to_equity = _safe_series_metric(analyzer, "debt_to_equity", DEFAULT_WEIGHT_QUANT, 5)
    interest_coverage = _safe_series_metric(
        analyzer, "interest_coverage", DEFAULT_WEIGHT_QUANT, 5
    )
    cash = analyzer.get_strict_mrq("cash_and_equivalents")
    debt = analyzer.get_strict_mrq("interest_bearing_debt")

    health_points = 0.0
    health_components: Dict[str, Any] = {}

    if debt_to_equity is not None and debt_to_equity < 1.0:
        debt_points = 4.0
    elif debt_to_equity is not None and debt_to_equity < 2.0:
        debt_points = 2.0
    else:
        debt_points = 0.0
    health_components["debt_to_equity_lt_1"] = {
        "value": debt_to_equity,
        "threshold": 1.0,
        "points": debt_points,
        "max_points": 4.0,
    }
    health_points += debt_points

    if interest_coverage is not None and interest_coverage > 5.0:
        coverage_points = 4.0
    elif interest_coverage is not None and interest_coverage > 2.0:
        coverage_points = 2.0
    else:
        coverage_points = 0.0
    health_components["interest_coverage_gt_10x"] = {
        "value": interest_coverage,
        "threshold": 5.0,
        "points": coverage_points,
        "max_points": 4.0,
        "note": "Public edition uses a lighter minimum threshold than the private model.",
    }
    health_points += coverage_points

    if cash is not None and debt is not None and cash > debt:
        cash_points = 4.0
    elif debt in (None, 0) and cash is not None:
        cash_points = 2.0
    else:
        cash_points = 0.0
    health_components["cash_gt_debt"] = {
        "value": (cash, debt),
        "points": cash_points,
        "max_points": 4.0,
    }
    health_points += cash_points
    health_block = _build_public_score_block(
        "financial_health", health_points, 12.0, health_components
    )

    mos_value = float(margin_of_safety or 0.0)
    if mos_value >= 0.30:
        mos_points = 8.0
    elif mos_value >= 0.10:
        mos_points = 5.0
    elif mos_value > 0:
        mos_points = 2.0
    else:
        mos_points = 0.0
    valuation_buffer_block = _build_public_score_block(
        "valuation_buffer",
        mos_points,
        8.0,
        {
            "margin_of_safety_buffer": {
                "value": mos_value,
                "threshold": 0.10,
                "points": mos_points,
                "max_points": 8.0,
                "note": "Broad public-edition valuation buffer check",
            }
        },
    )

    quant_blocks = [
        growth_block,
        profitability_block,
        health_block,
        valuation_buffer_block,
    ]
    quant_total = sum(block.points for block in quant_blocks)
    quant_total = max(0.0, min(50.0, quant_total))

    if moat_score >= 3.5:
        moat_points = 15.0
        moat_label = "Wide Durable Moat"
    elif moat_score >= 2.0:
        moat_points = 10.0
        moat_label = "Strong Moat"
    elif moat_score > 0:
        moat_points = 5.0
        moat_label = "Narrow Moat"
    else:
        moat_points = 0.0
        moat_label = "No Moat"
    moat_block = _build_public_score_block(
        "moat",
        moat_points,
        15.0,
        {
            "moat_rating": {
                "rating": moat_label,
                "moat_score": moat_score,
                "points": moat_points,
                "max_points": 15.0,
                "note": "Broad public-edition moat summary",
            }
        },
    )

    business_model_text = _extract_signal_text(
        _fetch_confident_value(analyzer, "business_model")
        or getattr(analyzer, "qual_summary", {}).get("business_model")
    )
    candor_level = _normalize_signal_level(
        _fetch_confident_value(analyzer, "management_candor")
        or getattr(analyzer, "qual_summary", {}).get("management_candor")
    )
    simplicity_level = _normalize_signal_level(
        _fetch_confident_value(analyzer, "ham_sandwich_test")
        or getattr(analyzer, "qual_summary", {}).get("ham_sandwich_test")
    )

    management_points = 0.0
    management_components: Dict[str, Any] = {}

    if "high" in candor_level:
        candor_points = 6.0
    elif "moderate" in candor_level or "medium" in candor_level:
        candor_points = 3.0
    else:
        candor_points = 0.0
    management_components["management_candor"] = {
        "value": candor_level or None,
        "points": candor_points,
        "max_points": 6.0,
    }
    management_points += candor_points

    if "simple" in simplicity_level:
        simplicity_points = 4.0
    elif "moderate" in simplicity_level:
        simplicity_points = 2.0
    else:
        simplicity_points = 0.0
    management_components["is_simple_and_understandable"] = {
        "value": simplicity_level or None,
        "points": simplicity_points,
        "max_points": 4.0,
    }
    management_points += simplicity_points

    if len(business_model_text) >= 80:
        business_model_points = 5.0
    elif len(business_model_text) >= 20:
        business_model_points = 3.0
    else:
        business_model_points = 0.0
    management_components["business_model_clarity"] = {
        "value": business_model_text or None,
        "points": business_model_points,
        "max_points": 5.0,
    }
    management_points += business_model_points
    management_block = _build_public_score_block(
        "management_quality", management_points, 15.0, management_components
    )

    pricing_level = _normalize_signal_level(
        _fetch_confident_value(analyzer, "pricing_power")
        or getattr(analyzer, "qual_summary", {}).get("pricing_power")
    )
    risk_tags = _fetch_confident_value(analyzer, "business_risk_tags") or []
    if isinstance(risk_tags, dict):
        risk_tags = risk_tags.get("value", [])
    risk_tags_set = set(str(tag).upper() for tag in risk_tags or [])

    market_position_points = 0.0
    market_position_components: Dict[str, Any] = {}

    if "high" in pricing_level or "strong" in pricing_level:
        pricing_points = 5.0
    elif "moderate" in pricing_level or "medium" in pricing_level:
        pricing_points = 3.0
    elif pricing_level:
        pricing_points = 1.0
    else:
        pricing_points = 0.0
    market_position_components["pricing_power"] = {
        "value": pricing_level or None,
        "points": pricing_points,
        "max_points": 5.0,
    }
    market_position_points += pricing_points

    if len(risk_tags_set) == 0:
        risk_points = 5.0
    elif len(risk_tags_set) == 1:
        risk_points = 3.0
    elif len(risk_tags_set) == 2:
        risk_points = 1.0
    else:
        risk_points = 0.0
    market_position_components["risk_tag_count"] = {
        "value": len(risk_tags_set),
        "points": risk_points,
        "max_points": 5.0,
        "note": "Fewer explicit risk tags receive more points in the public edition.",
    }
    market_position_points += risk_points
    market_position_block = _build_public_score_block(
        "market_position", market_position_points, 10.0, market_position_components
    )

    qualitative_blocks = [
        moat_block,
        management_block,
        market_position_block,
    ]
    qual_total = sum(block.points for block in qualitative_blocks)
    qual_total = max(0.0, min(40.0, qual_total))

    penalty_tags: Dict[str, float] = {}
    veto_triggered = False
    veto_reason = ""

    if "BLACK_BOX_ACCOUNTING" in risk_tags_set:
        penalty_tags["BLACK_BOX_ACCOUNTING"] = 10.0
        veto_triggered = True
        veto_reason = "Black Box Accounting"
    if (
        "ZERO_SUM_BUSINESS" in risk_tags_set
        or "ZERO_SUM_GAME" in risk_tags_set
        or "ZERO_SUM_ETHICAL" in risk_tags_set
    ):
        penalty_tags["ZERO_SUM_BUSINESS"] = 10.0
        veto_triggered = True
        veto_reason = veto_reason or "Zero Sum Business"
    if "KEY_PERSON_RISK" in risk_tags_set:
        penalty_tags["KEY_PERSON_RISK"] = max(
            penalty_tags.get("KEY_PERSON_RISK", 0.0), 3.0
        )
    if "REGULATORY_UNPREDICTABLE" in risk_tags_set:
        penalty_tags["REGULATORY_UNPREDICTABLE"] = max(
            penalty_tags.get("REGULATORY_UNPREDICTABLE", 0.0), 2.0
        )
    if "GEOPOLITICAL_RISK" in risk_tags_set or "SANCTION_RISK" in risk_tags_set:
        penalty_tags["EXTERNAL_RISK"] = max(penalty_tags.get("EXTERNAL_RISK", 0.0), 2.0)

    ethical_points = max(0.0, 10.0 - sum(penalty_tags.values()))
    ethical_block = _build_public_score_block(
        "ethical",
        ethical_points,
        10.0,
        {
            "penalty_tags": penalty_tags,
            "raw_tags": sorted(risk_tags_set),
        },
    )

    final_score = quant_total + qual_total + ethical_block.points
    final_score = max(0.0, min(100.0, final_score))

    if veto_triggered:
        print(f"[Conviction] Public-edition veto triggered by {veto_reason}. Score set to 0.")
        final_score = 0.0

    breakdown = {
        "final_score": round(float(final_score), 2),
        "public_edition": True,
        "quantitative": {
            "total": round(float(quant_total), 2),
            "max_points": 50.0,
            "blocks": {
                block.name: {
                    "points": round(float(block.points), 3),
                    "max_points": block.max_points,
                    "components": block.components,
                }
                for block in quant_blocks
            },
        },
        "qualitative": {
            "total": round(float(qual_total), 2),
            "max_points": 40.0,
            "blocks": {
                block.name: {
                    "points": round(float(block.points), 3),
                    "max_points": block.max_points,
                    "components": block.components,
                }
                for block in qualitative_blocks
            },
        },
        "ethical": {
            "points": round(float(ethical_block.points), 3),
            "max_points": 10.0,
            "components": ethical_block.components,
        },
        "final_dr": final_dr,
    }

    analyzer.checklist_results["conviction_breakdown"] = breakdown
    analyzer.checklist_results["conviction_score"] = round(float(final_score), 2)

    print(
        f"[Conviction] Public score={final_score} "
        f"(Quant={quant_total}/50, Qual={qual_total}/40, Ethical={ethical_block.points}/10)"
    )

    return round(float(final_score), 2)
