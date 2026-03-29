from typing import Dict


def is_fund_or_etf(analyzer) -> bool:
    industry = (analyzer.profile.get("industry") or "").strip().upper()
    summary = (analyzer.profile.get("longBusinessSummary") or "").upper()
    fund_industries = [
        "CLOSED-END FUND - DEBT", 
        "CLOSED-END FUND - EQUITY", 
        "CLOSED-END FUND - FOREIGN", 
        "EXCHANGE TRADED FUND"
    ]
    company_name = (analyzer.profile.get("company_name") or "").upper()
    
    return (
        industry in fund_industries or 
        "CLOSED-END FUND" in summary or 
        "EXCHANGE TRADED FUND" in summary or 
        "MUTUAL FUND" in summary or
        "FUND" in industry or
        "ETF" in industry or
        "FUND" in company_name or
        "ETF" in company_name
    )

def select_and_run_valuation_model(analyzer, discount_rate: float, net_cash: float = 0.0) -> Dict:
    """Select valuation model based on analyzer industry group and routing rules.
    """
    sector = (analyzer.profile.get("sector") or "").strip().upper()
    industry = (analyzer.profile.get("industry") or "").strip().upper()

    print(
        f"[Valuation Engine] Sector: {sector}, Industry: {industry}. Selecting appropriate model..."
    )

    summary = (analyzer.profile.get("longBusinessSummary") or "").upper()
    is_shell = industry == "SHELL COMPANIES" or "BLANK CHECK" in summary or "SHELL COMPANY" in summary

    if is_shell:
        print("[Valuation Engine] Strategy: Shell Company Valuation (Blocked)")
        return analyzer._run_shell_company_valuation()

    if is_fund_or_etf(analyzer):
        print("[Valuation Engine] Strategy: Fund NAV Valuation")
        return analyzer._run_fund_nav_valuation(model_label="Fund Net Asset Value (NAV)")

    is_insurance = "INSURANCE" in industry

    if sector == "FINANCIAL SERVICES" or is_insurance:
        if is_insurance:
            print("[Valuation Engine] Strategy: Insurance Earnings Power Model (Net Income Proxy)")
            return analyzer._run_conservative_fcfe_model(r=discount_rate)
        else:
            print("[Valuation Engine] Strategy: Bank Residual Income Model")
            return analyzer._run_residual_income_model_for_banks(discount_rate)

    # 2. Standard Fallback - using dynamically configured unified DCF engine
    print(f"[Valuation Engine] Strategy: Standard Owner Earnings DCF (Configured) | Net Cash: ${net_cash:,.0f}")
    return analyzer._run_dcf_valuation(discount_rate, net_cash=net_cash)
