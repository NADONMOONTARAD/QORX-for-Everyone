import pandas as pd

from backend.src.analysis_engine.checklist.conviction import (
    calculate_conviction_score,
    calculate_moat_score,
)


class StubAnalyzer:
    def __init__(self, *, qual_summary, profile, quant_df, confident_values, mrq_values):
        self.qual_summary = qual_summary
        self.profile = profile
        self.quant_df = quant_df
        self._confident_values = confident_values
        self._mrq_values = mrq_values
        self.checklist_results = {}

    def robust_metric(self, series, _weight_quant, window=None):
        values = pd.to_numeric(series, errors="coerce").dropna()
        if window:
            values = values.tail(window)
        if values.empty:
            return None
        return float(values.mean())

    def get_strict_mrq(self, key):
        return self._mrq_values.get(key)

    def _get_confident_value(self, key, _minimum_confidence):
        return self._confident_values.get(key), 1.0


def _build_quant_df():
    return pd.DataFrame(
        {
            "report_date": pd.to_datetime(
                [
                    "2020-12-31",
                    "2021-12-31",
                    "2022-12-31",
                    "2023-12-31",
                    "2024-12-31",
                ]
            ),
            "period_type": ["A", "A", "A", "A", "A"],
            "revenue_growth": [0.10, 0.12, 0.15, 0.11, 0.14],
            "roic": [0.18, 0.17, 0.20, 0.19, 0.18],
            "net_profit_margin": [0.12, 0.11, 0.13, 0.12, 0.14],
            "debt_to_equity": [0.4, 0.5, 0.45, 0.35, 0.4],
            "interest_coverage": [8.0, 7.0, 9.0, 8.5, 8.2],
        }
    )


def test_public_moat_score_uses_simple_transparent_weights():
    analyzer = StubAnalyzer(
        qual_summary={
            "moats_identified": [
                {"type": "Network Effect", "strength": "Strong"},
                {"type": "Switching Cost", "strength": "Moderate"},
            ]
        },
        profile={},
        quant_df=pd.DataFrame(),
        confident_values={},
        mrq_values={},
    )

    score, rating = calculate_moat_score(analyzer)

    assert score == 2.5
    assert rating == "Strong Moat"


def test_public_conviction_score_writes_breakdown_and_stays_in_range():
    analyzer = StubAnalyzer(
        qual_summary={
            "moats_identified": [
                {"type": "Network Effect", "strength": "Strong"},
                {"type": "Switching Cost", "strength": "Strong"},
            ]
        },
        profile={"sector": "Technology"},
        quant_df=_build_quant_df(),
        confident_values={
            "business_model": (
                "The company sells subscription software with recurring revenue, high retention, "
                "and low marginal cost across a broad enterprise customer base."
            ),
            "management_candor": "High",
            "ham_sandwich_test": "Simple",
            "pricing_power": "High",
            "business_risk_tags": [],
        },
        mrq_values={
            "cash_and_equivalents": 200.0,
            "interest_bearing_debt": 50.0,
        },
    )

    score = calculate_conviction_score(
        analyzer, moat_score=3.5, margin_of_safety=0.25, final_dr=0.1
    )

    breakdown = analyzer.checklist_results["conviction_breakdown"]

    assert 0.0 <= score <= 100.0
    assert score == analyzer.checklist_results["conviction_score"]
    assert breakdown["public_edition"] is True
    assert breakdown["quantitative"]["blocks"]["growth"]["points"] == 14.0
    assert breakdown["qualitative"]["blocks"]["moat"]["components"]["moat_rating"]["rating"] == "Wide Durable Moat"
    assert breakdown["ethical"]["components"]["penalty_tags"] == {}


def test_public_conviction_score_applies_zero_sum_veto():
    analyzer = StubAnalyzer(
        qual_summary={"moats_identified": []},
        profile={"sector": "Technology"},
        quant_df=_build_quant_df(),
        confident_values={
            "business_model": "Simple software business.",
            "management_candor": "Moderate",
            "ham_sandwich_test": "Simple",
            "pricing_power": "Medium",
            "business_risk_tags": ["ZERO_SUM_BUSINESS"],
        },
        mrq_values={
            "cash_and_equivalents": 200.0,
            "interest_bearing_debt": 50.0,
        },
    )

    score = calculate_conviction_score(
        analyzer, moat_score=0.0, margin_of_safety=0.2, final_dr=0.1
    )

    breakdown = analyzer.checklist_results["conviction_breakdown"]

    assert score == 0.0
    assert breakdown["final_score"] == 0.0
    assert breakdown["ethical"]["components"]["penalty_tags"]["ZERO_SUM_BUSINESS"] == 10.0

