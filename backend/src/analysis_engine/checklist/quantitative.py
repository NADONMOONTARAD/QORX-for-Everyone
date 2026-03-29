import pandas as pd
from typing import Tuple

from backend.src.analysis_engine.valuation.dr_engine import DEFAULT_WEIGHT_QUANT
from backend.src.analysis_engine.checklist.conviction import _safe_series_metric


def run_quantitative_health_check(analyzer) -> Tuple[float, dict]:
    """Performs the quantitative health check using the analyzer context.

    This function mirrors the previous InvestmentChecklistAnalyzer._run_quantitative_health_check
    but operates as a standalone function that accepts the analyzer instance.
    """
    print("[Checklist] Running comprehensive Quantitative Health Check...")
    results = {
        "growth": {},
        "profitability_quality": {},
        "financial_health": {},
        "shareholder_friendliness": {},
    }

    if len(analyzer.quant_df) < 2:
        return 0.05, {"note": "Insufficient data for full quantitative check."}

    # --- Dynamic threshold setup ---
    weight_quant = DEFAULT_WEIGHT_QUANT

    sector = (analyzer.profile.get("sector") or "").strip().upper()
    industry = (analyzer.profile.get("industry") or "").strip().upper()
    is_reit = sector == "REAL ESTATE" or "REIT" in industry or "REAL ESTATE INVESTMENT TRUST" in industry
    is_fund = "FUND" in industry or "ETF" in industry or "EXCHANGE TRADED" in industry

    orig_sector = analyzer.profile.get("sector")
    orig_industry = analyzer.profile.get("industry")
    from backend.src.analysis_engine.valuation.industry_config import get_dcf_config
    try:
        dcf_config = get_dcf_config(orig_sector, orig_industry)
        base_metric = dcf_config.get("metric", "FCF")
    except Exception:
        base_metric = "FCF"

    is_fcf_exempt = (base_metric == "NET_INCOME") or is_fund
    is_cashflow_health_exempt = (base_metric == "NET_INCOME") or is_reit or is_fund

    # --- Growth Checks ---
    rev_growth = analyzer.robust_metric(
        analyzer.quant_df.get("revenue_growth", pd.Series()), weight_quant
    )
    eps_growth = analyzer.robust_metric(
        analyzer.quant_df.get("eps_growth_diluted", pd.Series()), weight_quant
    )
    fcf_growth = analyzer.robust_metric(
        analyzer.quant_df.get("fcf_growth", pd.Series()), weight_quant
    )

    if is_fund:
        results["growth"]["revenue_growth_gt_10_pct"] = {"pass": True, "value": "N/A (Fund)", "note": "Fund exempt"}
        results["growth"]["eps_growth_gt_10_pct"] = {"pass": True, "value": "N/A (Fund)", "note": "Fund exempt"}
    else:
        results["growth"]["revenue_growth_gt_10_pct"] = {"pass": (rev_growth is not None and rev_growth > 0.10), "value": rev_growth}
        results["growth"]["eps_growth_gt_10_pct"] = {"pass": (eps_growth is not None and eps_growth > 0.10), "value": eps_growth}

    if is_fcf_exempt:
        results["growth"]["fcf_growth_gt_8_pct"] = {
            "pass": True,
            "value": "N/A (Industry/Fund)",
            "note": "FCF metrics skipped for Net Income-based sectors and Funds",
        }
    else:
        results["growth"]["fcf_growth_gt_8_pct"] = {
            "pass": (fcf_growth is not None and fcf_growth > 0.08),
            "value": fcf_growth,
        }

    # --- Profitability & Quality ---
    # Use _safe_series_metric to ensure ratio metrics use Annual (10-K) data only
    roe = _safe_series_metric(analyzer, "roe", weight_quant)
    roic = _safe_series_metric(analyzer, "roic", weight_quant)
    gross_margin = _safe_series_metric(analyzer, "gross_margin", weight_quant)
    net_margin = _safe_series_metric(analyzer, "net_profit_margin", weight_quant)
    fcf_margin = _safe_series_metric(analyzer, "fcf_margin", weight_quant)

    if is_fund:
        results["profitability_quality"]["roe_gt_15_pct"] = {"pass": True, "value": "N/A (Fund)", "note": "Fund exempt"}
        results["profitability_quality"]["roic_gt_12_pct"] = {"pass": True, "value": "N/A (Fund)", "note": "Fund exempt"}
        results["profitability_quality"]["gross_margin_gt_20_pct"] = {"pass": True, "value": "N/A (Fund)", "note": "Fund exempt"}
        results["profitability_quality"]["net_margin_gt_10_pct"] = {"pass": True, "value": "N/A (Fund)", "note": "Fund exempt"}
    else:
        results["profitability_quality"]["roe_gt_15_pct"] = {"pass": (roe is not None and roe > 0.15), "value": roe}
        results["profitability_quality"]["roic_gt_12_pct"] = {"pass": (roic is not None and roic > 0.12), "value": roic}
        results["profitability_quality"]["gross_margin_gt_20_pct"] = {"pass": (gross_margin is not None and gross_margin > 0.20), "value": gross_margin}
        results["profitability_quality"]["net_margin_gt_10_pct"] = {"pass": (net_margin is not None and net_margin > 0.10), "value": net_margin}

    if is_fcf_exempt:
        results["profitability_quality"]["fcf_margin_gt_10_pct"] = {
            "pass": True,
            "value": "N/A (Industry/Fund)",
            "note": "FCF metrics skipped for Net Income-based sectors and Funds",
        }
    else:
        results["profitability_quality"]["fcf_margin_gt_10_pct"] = {
            "pass": (fcf_margin is not None and fcf_margin > 0.10),
            "value": fcf_margin,
        }

    # --- Financial Health ---
    d_to_e = analyzer.get_strict_mrq("debt_to_equity")
    cash = analyzer.get_strict_mrq("cash_and_equivalents")
    debt = analyzer.get_strict_mrq("interest_bearing_debt")
    int_cov = _safe_series_metric(analyzer, "interest_coverage", weight_quant)

    # Exempt Banks, Insurance, Utilities, REIT, and Funds from D/E check
    is_de_exempt = (base_metric == "NET_INCOME") or sector in ["FINANCIAL SERVICES", "UTILITIES"] or is_reit or is_fund
    if is_de_exempt:
        results["financial_health"]["debt_to_equity_lt_1"] = {
            "pass": True,
            "value": d_to_e,
            "note": "Industry/Fund exempt from D/E threshold",
        }
    else:
        results["financial_health"]["debt_to_equity_lt_1"] = {
            "pass": (d_to_e is not None and d_to_e < 1.0),
            "value": d_to_e,
        }

    if is_cashflow_health_exempt:
        results["financial_health"]["interest_coverage_gt_10x"] = {
            "pass": True,
            "value": "N/A (Industry/Fund)",
            "note": "Industry/Fund exempt from Int. Coverage",
        }
        results["financial_health"]["cash_gt_debt"] = {
            "pass": True,
            "value": "N/A (Industry/Fund)",
            "note": "Industry/Fund exempt from Cash > Debt",
        }
    else:
        results["financial_health"]["interest_coverage_gt_10x"] = {
            "pass": (int_cov is not None and int_cov > 10),
            "value": int_cov,
        }
        results["financial_health"]["cash_gt_debt"] = {
            "pass": (cash is not None and debt is not None and cash > debt),
            "value": f"{cash}/{debt}",
        }

    # --- Shareholder Friendliness ---
    try:
        qdf = analyzer.quant_df
        shares = (
            qdf[qdf.get("period_type", "A") == "A"]
            .get("share_outstanding_diluted", pd.Series())
            .dropna()
            .tail(2)
        )
        if len(shares) == 2 and shares.iloc[0] > 0:
            dilution = (shares.iloc[1] / shares.iloc[0]) - 1.0
        else:
            dilution = None
    except Exception:
        dilution = None

    pass_low_dilution = dilution is not None and dilution < 0.03
    results["shareholder_friendliness"]["dilution_lt_3_pct"] = {
        "pass": pass_low_dilution,
        "value": dilution,
    }

    return 0.0, results
