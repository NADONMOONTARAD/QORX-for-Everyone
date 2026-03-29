from backend.src.analysis_engine.checklist.val_dispatcher import (
    is_fund_or_etf,
    select_and_run_valuation_model,
)


class StubAnalyzer:
    def __init__(self, profile):
        self.profile = profile
        self.calls = []

    def _run_shell_company_valuation(self):
        self.calls.append(("shell",))
        return {"route": "shell"}

    def _run_fund_nav_valuation(self, model_label=""):
        self.calls.append(("fund", model_label))
        return {"route": "fund", "model_label": model_label}

    def _run_conservative_fcfe_model(self, r):
        self.calls.append(("insurance", r))
        return {"route": "insurance", "discount_rate": r}

    def _run_residual_income_model_for_banks(self, r):
        self.calls.append(("bank", r))
        return {"route": "bank", "discount_rate": r}

    def _run_dcf_valuation(self, discount_rate, net_cash=0.0):
        self.calls.append(("dcf", discount_rate, net_cash))
        return {"route": "dcf", "discount_rate": discount_rate, "net_cash": net_cash}


def test_is_fund_or_etf_detects_fund_from_industry_and_company_name():
    by_industry = StubAnalyzer(
        {"industry": "Exchange Traded Fund", "company_name": "Anything"}
    )
    by_name = StubAnalyzer(
        {"industry": "Asset Management", "company_name": "Global ETF Holdings"}
    )

    assert is_fund_or_etf(by_industry) is True
    assert is_fund_or_etf(by_name) is True


def test_select_and_run_valuation_model_routes_shell_companies_first():
    analyzer = StubAnalyzer(
        {
            "sector": "Financial Services",
            "industry": "Shell Companies",
            "longBusinessSummary": "Blank check company seeking acquisition",
        }
    )

    result = select_and_run_valuation_model(analyzer, discount_rate=0.11, net_cash=100)

    assert result["route"] == "shell"
    assert analyzer.calls == [("shell",)]


def test_select_and_run_valuation_model_routes_funds_to_nav():
    analyzer = StubAnalyzer(
        {
            "sector": "Financial Services",
            "industry": "Exchange Traded Fund",
            "company_name": "Index ETF",
        }
    )

    result = select_and_run_valuation_model(analyzer, discount_rate=0.11, net_cash=100)

    assert result["route"] == "fund"
    assert analyzer.calls == [("fund", "Fund Net Asset Value (NAV)")]


def test_select_and_run_valuation_model_routes_insurance_to_insurance_model():
    analyzer = StubAnalyzer(
        {
            "sector": "Financial Services",
            "industry": "Insurance - Life",
        }
    )

    result = select_and_run_valuation_model(analyzer, discount_rate=0.12, net_cash=0)

    assert result["route"] == "insurance"
    assert analyzer.calls == [("insurance", 0.12)]


def test_select_and_run_valuation_model_routes_financials_to_bank_model():
    analyzer = StubAnalyzer(
        {
            "sector": "Financial Services",
            "industry": "Banks - Regional",
        }
    )

    result = select_and_run_valuation_model(analyzer, discount_rate=0.13, net_cash=0)

    assert result["route"] == "bank"
    assert analyzer.calls == [("bank", 0.13)]


def test_select_and_run_valuation_model_routes_non_financials_to_standard_dcf():
    analyzer = StubAnalyzer(
        {
            "sector": "Technology",
            "industry": "Software - Infrastructure",
        }
    )

    result = select_and_run_valuation_model(analyzer, discount_rate=0.1, net_cash=250.0)

    assert result["route"] == "dcf"
    assert analyzer.calls == [("dcf", 0.1, 250.0)]
