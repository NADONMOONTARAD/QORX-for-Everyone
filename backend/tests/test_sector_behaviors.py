import pandas as pd

from backend.src.analysis_engine.checklist.quantitative import (
    run_quantitative_health_check,
)


class QuantAnalyzerStub:
    def __init__(self, profile, rows):
        self.profile = profile
        self.quant_df = pd.DataFrame(rows)
        self.quant_df["report_date"] = pd.to_datetime(self.quant_df["report_date"])

    def robust_metric(self, series, weight_quant, window=None):
        cleaned = pd.to_numeric(series, errors="coerce").dropna()
        if window is not None and window > 0:
            cleaned = cleaned.tail(window)
        if cleaned.empty:
            return None
        return float(cleaned.iloc[-1])

    def get_strict_mrq(self, key):
        if key not in self.quant_df.columns:
            return None
        cleaned = pd.to_numeric(self.quant_df[key], errors="coerce").dropna()
        if cleaned.empty:
            return None
        return float(cleaned.iloc[-1])


def _base_rows():
    return [
        {
            "period_type": "A",
            "report_date": "2023-12-31",
            "revenue_growth": 0.11,
            "eps_growth_diluted": 0.12,
            "fcf_growth": 0.09,
            "roe": 0.16,
            "roic": 0.13,
            "gross_margin": 0.45,
            "net_profit_margin": 0.18,
            "fcf_margin": 0.16,
            "debt_to_equity": 0.8,
            "cash_and_equivalents": 150.0,
            "interest_bearing_debt": 100.0,
            "interest_coverage": 12.0,
            "share_outstanding_diluted": 1000.0,
        },
        {
            "period_type": "A",
            "report_date": "2024-12-31",
            "revenue_growth": 0.13,
            "eps_growth_diluted": 0.15,
            "fcf_growth": 0.14,
            "roe": 0.18,
            "roic": 0.15,
            "gross_margin": 0.47,
            "net_profit_margin": 0.19,
            "fcf_margin": 0.18,
            "debt_to_equity": 0.7,
            "cash_and_equivalents": 220.0,
            "interest_bearing_debt": 120.0,
            "interest_coverage": 14.0,
            "share_outstanding_diluted": 990.0,
        },
    ]


def test_standard_technology_sector_uses_real_threshold_checks():
    analyzer = QuantAnalyzerStub(
        {"sector": "Technology", "industry": "Software - Application"},
        _base_rows(),
    )

    _, results = run_quantitative_health_check(analyzer)

    assert results["growth"]["fcf_growth_gt_8_pct"]["pass"] is True
    assert results["financial_health"]["cash_gt_debt"]["pass"] is True
    assert results["financial_health"]["interest_coverage_gt_10x"]["pass"] is True
    assert results["financial_health"]["debt_to_equity_lt_1"]["pass"] is True


def test_bank_sector_exempts_fcf_and_cashflow_health_checks():
    analyzer = QuantAnalyzerStub(
        {"sector": "Financial Services", "industry": "Banks - Regional"},
        _base_rows(),
    )

    _, results = run_quantitative_health_check(analyzer)

    assert results["growth"]["fcf_growth_gt_8_pct"]["note"].startswith("FCF metrics skipped")
    assert results["profitability_quality"]["fcf_margin_gt_10_pct"]["note"].startswith("FCF metrics skipped")
    assert results["financial_health"]["cash_gt_debt"]["note"].startswith("Industry/Fund exempt")
    assert results["financial_health"]["interest_coverage_gt_10x"]["note"].startswith("Industry/Fund exempt")
    assert results["financial_health"]["debt_to_equity_lt_1"]["note"].startswith("Industry/Fund exempt")


def test_reit_sector_keeps_fcf_checks_but_exempts_cashflow_health():
    analyzer = QuantAnalyzerStub(
        {"sector": "Real Estate", "industry": "REIT - Industrial"},
        _base_rows(),
    )

    _, results = run_quantitative_health_check(analyzer)

    assert results["growth"]["fcf_growth_gt_8_pct"]["pass"] is True
    assert results["profitability_quality"]["fcf_margin_gt_10_pct"]["pass"] is True
    assert results["financial_health"]["cash_gt_debt"]["note"].startswith("Industry/Fund exempt")
    assert results["financial_health"]["interest_coverage_gt_10x"]["note"].startswith("Industry/Fund exempt")
    assert results["financial_health"]["debt_to_equity_lt_1"]["note"].startswith("Industry/Fund exempt")


def test_fund_sector_exempts_growth_profitability_and_health_thresholds():
    analyzer = QuantAnalyzerStub(
        {"sector": "Financial Services", "industry": "Exchange Traded Fund"},
        _base_rows(),
    )

    _, results = run_quantitative_health_check(analyzer)

    assert results["growth"]["revenue_growth_gt_10_pct"]["note"] == "Fund exempt"
    assert results["growth"]["eps_growth_gt_10_pct"]["note"] == "Fund exempt"
    assert results["profitability_quality"]["roe_gt_15_pct"]["note"] == "Fund exempt"
    assert results["financial_health"]["cash_gt_debt"]["note"].startswith("Industry/Fund exempt")


def test_utilities_sector_only_exempts_debt_to_equity_rule():
    rows = _base_rows()
    rows[-1]["cash_and_equivalents"] = 80.0
    rows[-1]["interest_bearing_debt"] = 120.0
    rows[-1]["interest_coverage"] = 9.0

    analyzer = QuantAnalyzerStub(
        {"sector": "Utilities", "industry": "Utilities - Regulated Electric"},
        rows,
    )

    _, results = run_quantitative_health_check(analyzer)

    assert results["financial_health"]["debt_to_equity_lt_1"]["note"].startswith("Industry/Fund exempt")
    assert results["financial_health"]["cash_gt_debt"]["pass"] is False
    assert results["financial_health"]["interest_coverage_gt_10x"]["pass"] is False
