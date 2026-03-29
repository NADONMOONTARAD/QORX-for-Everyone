"""Pure financial-processing helpers extracted from daily_analysis_job.
These functions are deterministic and free of DB side-effects so they can be
unit-tested independently.
"""

from typing import List
from backend.src.jobs.helpers import (
    get_financial_concept,
    safe_sum,
    safe_subtract,
    to_int,
)


def _update_if_value(target: dict, key: str, *candidates):
    """Assigns the first non-None candidate converted to int into target[key]."""
    for candidate in candidates:
        if candidate is None:
            continue
        value = to_int(candidate)
        if value is not None:
            target[key] = value
            return


def process_finnhub_financials(finnhub_financials: dict, ticker: str) -> List[dict]:
    if not finnhub_financials or "data" not in finnhub_financials:
        return []
    records = []

    for report in finnhub_financials["data"]:
        ic = {
            item["concept"]: item["value"]
            for item in report.get("report", {}).get("ic", [])
        }
        bs = {
            item["concept"]: item["value"]
            for item in report.get("report", {}).get("bs", [])
        }
        cf = {
            item["concept"]: item["value"]
            for item in report.get("report", {}).get("cf", [])
        }

        buyback_cost = get_financial_concept(
            cf, ["us-gaap_PaymentsForRepurchaseOfCommonStock"]
        )
        if buyback_cost is not None:
            buyback_cost = abs(buyback_cost)

        record = {
            "ticker": ticker,
            "report_date": report.get("endDate"),
            "period_type": "A",
            "total_revenue": get_financial_concept(
                ic,
                [
                    "us-gaap_Revenues",
                    "us-gaap_RevenuesNetOfInterestExpense",
                    "us-gaap_OperatingRevenue",
                    "us-gaap_RevenueFromContractWithCustomerExcludingAssessedTax",
                ],
            ),
            "net_income": get_financial_concept(
                ic,
                [
                    "us-gaap_NetIncomeLoss",
                    "us-gaap_NetIncomeLossAvailableToCommonStockholdersDiluted",
                    "us-gaap_NetIncomeLossAvailableToCommonStockholdersBasic",
                ],
            ),
            "total_assets": get_financial_concept(bs, ["us-gaap_Assets"]),
            "total_liabilities": (
                get_financial_concept(bs, ["us-gaap_Liabilities"])
                or safe_sum(
                    [
                        get_financial_concept(bs, ["us-gaap_LiabilitiesCurrent"]),
                        get_financial_concept(bs, ["us-gaap_LiabilitiesNoncurrent"]),
                    ]
                )
            ),
            "share_outstanding_diluted": get_financial_concept(
                ic,
                [
                    "us-gaap_WeightedAverageNumberOfDilutedSharesOutstanding",
                    "us-gaap_WeightedAverageNumberOfSharesOutstandingDiluted",
                ],
            ),
            "operating_income": get_financial_concept(
                ic,
                [
                    "us-gaap_OperatingIncomeLoss",
                    "us-gaap_IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
                ],
            ),
            "income_tax_expense": get_financial_concept(
                ic, ["us-gaap_IncomeTaxExpenseBenefit", "us-gaap_TaxProvision"]
            ),
            "cash_flow_from_operations": get_financial_concept(
                cf, ["us-gaap_NetCashProvidedByUsedInOperatingActivities"]
            ),
            "capital_expenditures": get_financial_concept(
                cf,
                [
                    # Standard CapEx tag (non-REIT)
                    "us-gaap_PaymentsToAcquirePropertyPlantAndEquipment",
                    "us-gaap_PaymentsToAcquireProductiveAssets",
                    # REIT: Total property acquisition spend (Growth + Maintenance combined)
                    # NOTE: us-gaap_PaymentsForCapitalImprovements is intentionally excluded.
                    # It represents only Maintenance CapEx and is a known manipulation vector
                    # (managers can reclassify maintenance as growth to inflate AFFO).
                    # We always use Total CapEx (CFO - SBC - TotalCapEx) for conservative AFFO.
                    "us-gaap_PaymentsToAcquireRealEstate",
                    "us-gaap_PaymentsToAcquireCommercialRealEstate",
                    "us-gaap_PaymentsToAcquireAndDevelopRealEstate",
                ],
            ),
            "gross_profit": (
                get_financial_concept(ic, ["us-gaap_GrossProfit"])
                or safe_subtract(
                    get_financial_concept(
                        ic,
                        ["us-gaap_RevenueFromContractWithCustomerExcludingAssessedTax"],
                    ),
                    get_financial_concept(ic, ["us-gaap_CostOfGoodsAndServicesSold"]),
                )
            ),
            "interest_expense": get_financial_concept(
                ic,
                [
                    "us-gaap_InterestExpense",
                    "us-gaap_InterestAndDebtExpense",
                    "us-gaap_InterestExpenseOperating",
                    "us-gaap_InterestExpenseNonoperating",
                    "us-gaap_InterestIncomeExpenseNonoperatingNet",
                ],
            ),
            "interest_bearing_debt": safe_sum(
                [
                    get_financial_concept(bs, ["us-gaap_CommercialPaper"]),
                    get_financial_concept(
                        bs,
                        [
                            "us-gaap_LongTermDebtAndCapitalLeaseObligationsIncludingCurrentMaturities",
                        ],
                    )
                    or safe_sum(
                        [
                            get_financial_concept(bs, ["us-gaap_LongTermDebtCurrent"]),
                            get_financial_concept(
                                bs, ["us-gaap_LongTermDebtNoncurrent"]
                            ),
                        ]
                    ),
                    get_financial_concept(
                        bs, ["us-gaap_LongTermDebtAndCapitalLeaseObligations"]
                    ),
                    get_financial_concept(bs, ["us-gaap_LinesOfCreditCurrent"]),
                    get_financial_concept(bs, ["us-gaap_LongTermLineOfCredit"]),
                    get_financial_concept(bs, ["us-gaap_LongTermNotesPayable"]),
                    get_financial_concept(bs, ["us-gaap_NotesPayable"]),
                    get_financial_concept(
                        bs, ["us-gaap_ConvertibleLongTermNotesPayable"]
                    ),
                    get_financial_concept(bs, ["us-gaap_LoansPayable"]),
                    get_financial_concept(bs, ["us-gaap_SecuredDebt"]),
                    get_financial_concept(bs, ["o_LineOfCreditAndCommercialPaper"]),
                ],
            ),
            "cash_and_equivalents": get_financial_concept(
                bs,
                [
                    "us-gaap_CashAndCashEquivalentsAtCarryingValue",
                    "us-gaap_Cash",
                ],
            )
            or get_financial_concept(
                cf,
                [
                    "us-gaap_CashAndCashEquivalentsAtCarryingValue",
                    "us-gaap_CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalentsPeriodIncreaseDecreaseIncludingExchangeRateEffect",
                ],
            ),
            "goodwill_and_intangibles": (
                safe_sum(
                    [
                        get_financial_concept(bs, ["us-gaap_Goodwill"]),
                        get_financial_concept(
                            bs, ["us-gaap_IntangibleAssetsNetExcludingGoodwill"]
                        ),
                    ]
                )
                or get_financial_concept(
                    bs,
                    ["jpm_GoodwillServicingAssetsatFairValueandOtherIntangibleAssets"],
                )
            ),
            "selling_general_and_admin_expense": (
                safe_sum(
                    [
                        get_financial_concept(ic, ["us-gaap_LaborAndRelatedExpense"]),
                        get_financial_concept(ic, ["us-gaap_OccupancyNet"]),
                        get_financial_concept(
                            ic, ["us-gaap_CommunicationsAndInformationTechnology"]
                        ),
                        get_financial_concept(
                            ic, ["us-gaap_ProfessionalAndContractServicesExpense"]
                        ),
                        get_financial_concept(
                            ic, ["us-gaap_MarketingAndAdvertisingExpense"]
                        ),
                        get_financial_concept(
                            ic, ["us-gaap_GeneralAndAdministrativeExpense"]
                        ),
                    ]
                )
                or get_financial_concept(
                    ic,
                    [
                        "us-gaap_SellingGeneralAndAdministrativeExpense",
                        "kalu_SellingAdministrativeResearchAndDevelopmentAndGeneralExpenses",
                    ],
                )
            ),
            "depreciation_and_amortization": (
                get_financial_concept(
                    cf,
                    [
                        "us-gaap_DepreciationDepletionAndAmortization",
                        "us-gaap_DepreciationAmortizationAndAccretionNet",
                        "us-gaap_DepreciationAndAmortization",
                    ],
                )
                or get_financial_concept(
                    ic,
                    [
                        "us-gaap_DepreciationDepletionAndAmortization",
                        "us-gaap_DepreciationAmortizationAndAccretionNet",
                    ],
                )
            ),
            "dividends_paid": (
                get_financial_concept(cf, ["us-gaap_PaymentsOfDividendsCommonStock"])
                or get_financial_concept(cf, ["us-gaap_PaymentsOfDividends"])
                or get_financial_concept(cf, ["us-gaap_CashDividendsPaid"])
            ),
            "accounts_receivable": get_financial_concept(
                bs,
                [
                    "us-gaap_AccountsReceivableNet",
                    "us-gaap_AccountsReceivableNetCurrent",
                    "jpm_AccruedInterestAndAccountsReceivable",
                ],
            ),
            "unearned_premiums": get_financial_concept(
                bs,
                [
                    "us-gaap_DeferredRevenueCurrent",
                ],
            ),
            "medical_costs_payable": get_financial_concept(
                bs,
                [
                    "us-gaap_LiabilityForClaimsAndClaimsAdjustmentExpense",
                ],
            ),
            "accounts_payable": get_financial_concept(
                bs,
                [
                    "us-gaap_AccountsPayableCurrent",
                    "us-gaap_AccountsPayableAndAccruedLiabilitiesCurrentAndNoncurrent",
                    "us-gaap_AccountsPayableAndAccruedLiabilitiesCurrent",
                ],
            ),
            "total_stockholder_equity": get_financial_concept(
                bs, 
                [   
                    "us-gaap_StockholdersEquity", 
                    "us-gaap_StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
                ]
            ),
            "inventory": get_financial_concept(bs, ["us-gaap_InventoryNet"]),
            "other_non_cash_items": get_financial_concept(
                cf,
                [
                    "us-gaap_OtherNoncashIncomeExpense",
                    "us-gaap_OtherNoncashIncome",
                    "us-gaap_AmortizationOfDebtDiscountPremium",
                    "us-gaap_AmortizationOfFinancingCosts",
                    "o_OtherNoncashInterestIncomeExpenseOperating",
                    "us-gaap_AssetImpairmentCharges",
                    "us-gaap_OtherPostretirementBenefitsExpenseReversalOfExpenseNoncash",
                    "us-gaap_InventoryLIFOReserveEffectOnIncomeNet",
                ],
            ),
            "policy_acquisition_costs": safe_sum(
                [
                    get_financial_concept(
                        ic, ["us-gaap_AmortizationOfDeferredPolicyAcquisitionCosts"]
                    ),
                    get_financial_concept(
                        ic, ["us-gaap_DeferredPolicyAcquisitionCosts"]
                    ),
                ]
            ),
            "premiums_earned": get_financial_concept(ic, ["us-gaap_PremiumsEarnedNet"]),
            "losses_incurred": get_financial_concept(
                ic, ["us-gaap_PolicyholderBenefitsAndClaimsIncurredNet"]
            ),
            "property_plant_and_equipment_net": get_financial_concept(
                bs,
                [
                    "us-gaap_RealEstateInvestmentPropertyNet",
                    "us-gaap_PropertyPlantAndEquipmentNet",
                    "jpm_PropertyPlantAndEquipmentAndOperatingLeaseRightOfUseAssetAfterAccumulatedDepreciationAndAmortization",
                    "us-gaap_PropertyPlantAndEquipmentAndFinanceLeaseRightOfUseAssetAfterAccumulatedDepreciationAndAmortization",
                ],
            ),
            "stock_based_compensation": get_financial_concept(
                cf, ["us-gaap_ShareBasedCompensation"]
            ),
            "deferred_income_tax": (
                get_financial_concept(cf, ["us-gaap_DeferredIncomeTaxExpenseBenefit"])
                or get_financial_concept(
                    cf, ["us-gaap_DeferredIncomeTaxesAndTaxCredits"]
                )
                or get_financial_concept(
                    bs, ["us-gaap_DeferredIncomeTaxLiabilitiesNet"]
                )
            ),
            "current_assets": (
                get_financial_concept(bs, ["us-gaap_AssetsCurrent"])
                or safe_sum(
                    [
                        get_financial_concept(
                            bs, ["us-gaap_CashAndCashEquivalentsAtCarryingValue"]
                        ),
                        get_financial_concept(bs, ["us-gaap_AccountsReceivableNet"]),
                    ]
                )
            ),
            "current_liabilities": (
                get_financial_concept(bs, ["us-gaap_LiabilitiesCurrent"])
                or safe_sum(
                    [
                        (
                            get_financial_concept(
                                bs,
                                [
                                    "us-gaap_AccountsPayableAndAccruedLiabilitiesCurrent",
                                ],
                            )
                            or get_financial_concept(
                                bs,
                                [
                                    "us-gaap_AccountsPayableAndAccruedLiabilitiesCurrentAndNoncurrent",
                                ],
                            )
                        ),
                        (
                            get_financial_concept(
                                bs,
                                ["us-gaap_DividendsPayableCurrent"],
                            )
                            or get_financial_concept(
                                bs,
                                ["us-gaap_DividendsPayableCurrentAndNoncurrent"],
                            )
                        ),
                    ]
                )
            ),
            "total_cost_of_buybacks": buyback_cost,
        }

        records.append(record)

    return records


def _process_yfinance_set(reports: List[dict], period_type: str) -> List[dict]:
    merged_by_date = {}
    for report in reports:
        date_str = report.get("date")
        if not date_str:
            continue
        # Key by full date string (YYYY-MM-DD) for accuracy
        if date_str not in merged_by_date:
            merged_by_date[date_str] = {"report_date": date_str}
        
        target = merged_by_date[date_str]

        _update_if_value(target, "net_income", report.get("Net Income"))

        _update_if_value(
            target, "total_assets", report.get("Total Assets")
        )

        _update_if_value(
            target,
            "total_liabilities",
            report.get("Total Liabilities Net Minority Interest"),
        )

        _update_if_value(
            target,
            "share_outstanding_diluted",
            report.get("Diluted Average Shares"),
        )

        _update_if_value(
            target, "operating_income", report.get("Operating Income")
        )

        _update_if_value(
            target, "income_tax_expense", report.get("Tax Provision")
        )

        _update_if_value(
            target,
            "cash_flow_from_operations",
            report.get("Cash Flow From Continuing Operating Activities"),
        )

        capex = (
            to_int(report.get("Capital Expenditure"))
            or to_int(report.get("Capital Expenditures"))
            or to_int(report.get("CapitalExpenditure"))
            # REIT fallback: yfinance reports investment property purchases here
            # This is Total CapEx (Growth + Maintenance) — exactly what we want
            # for conservative CFO - SBC - TotalCapEx = Owner Earnings calculation
            or to_int(report.get("Purchase Of Investment Properties"))
        )
        if capex is not None:
            target["capital_expenditures"] = abs(capex)

        if target.get("total_cost_of_buybacks") is None:
            for candidate in (
                report.get("Common Stock Payments"),
                report.get("Net Common Stock Issuance"),
                report.get("Repurchase Of Capital Stock"),
            ):
                candidate_val = to_int(candidate)
                if candidate_val is not None:
                    target["total_cost_of_buybacks"] = abs(candidate_val)
                    break
                    
        _update_if_value(
            target, "cost_of_revenue", report.get("Cost Of Revenue")
        )

        _update_if_value(
            target, "gross_profit", report.get("Gross Profit")
        )

        _update_if_value(
            target, "interest_expense", report.get("Interest Expense")
        )

        _update_if_value(
            target,
            "cash_and_equivalents",
            report.get("Cash And Cash Equivalents"),
        )

        _update_if_value(
            target,
            "goodwill_and_intangibles",
            report.get("Goodwill And Other Intangible Assets"),
        )

        _update_if_value(
            target,
            "property_plant_and_equipment_net",
            report.get("Net PPE"),
        )

        _update_if_value(
            target,
            "accounts_receivable",
            report.get("Accounts Receivable"),
        )

        _update_if_value(target, "inventory", report.get("Inventory"))

        _update_if_value(
            target, "accounts_payable", report.get("Accounts Payable")
        )

        _update_if_value(
            target,
            "stock_based_compensation",
            report.get("Stock Based Compensation"),
            report.get("StockBasedCompensation"),
            report.get("Share Based Compensation"),
            report.get("ShareBasedCompensation"),
        )

        deferred_tax = (
            to_int(report.get("Deferred Income Tax"))
            or to_int(report.get("Deferred Tax"))
            or to_int(report.get("Non Current Deferred Taxes Liabilities"))
        )
        if deferred_tax is not None:
            target["deferred_income_tax"] = deferred_tax

        _update_if_value(
            target, "current_assets", report.get("Current Assets")
        )

        _update_if_value(
            target,
            "current_liabilities",
            report.get("Current Liabilities"),
        )

        _update_if_value(
            target,
            "total_stockholder_equity",
            report.get("Stockholders Equity"),
            report.get("Common Stock Equity"),
            report.get("Total Equity Gross Minority Interest"),
            report.get("Total Equity"),
        )

        interest_debt = safe_sum(
            [
                to_int(report.get("Commercial Paper")),
                to_int(report.get("Other Current Borrowings")),
                (
                    to_int(report.get("Long Term Debt"))
                    or to_int(report.get("Long Term Debt And Capital Lease Obligation"))
                ),
                to_int(report.get("Notes Payable")),
                to_int(report.get("Convertible Debt")),
            ]
        )
        if interest_debt is not None:
            target["interest_bearing_debt"] = interest_debt

        depreciation = (
            to_int(report.get("Depreciation And Amortization"))
            or to_int(report.get("Depreciation Amortization Depletion"))
            or to_int(report.get("Reconciled Depreciation"))
        )
        if depreciation is not None:
            target["depreciation_and_amortization"] = depreciation

        sga = (
            safe_sum(
                [
                    to_int(report.get("Salaries And Wages")),
                    to_int(report.get("Occupancy And Equipment")),
                    to_int(
                        report.get("Professional Expense And Contract Services Expense")
                    ),
                    to_int(report.get("Selling And Marketing Expense")),
                ]
            )
            or to_int(report.get("Selling General And Administration"))
            or to_int(report.get("General And Administrative Expense"))
        )
        if sga is not None:
            target["selling_general_and_admin_expense"] = sga

        dividends = (
            to_int(report.get("Cash Dividends Paid"))
            or to_int(report.get("Preferred Stock Dividends"))
            or to_int(report.get("Otherunder Preferred Stock Dividend"))
        )
        if dividends is not None:
            target["dividends_paid"] = dividends

        revenue = to_int(report.get("Total Revenue")) or to_int(
            report.get("Operating Revenue")
        )
        if revenue is not None:
            target["total_revenue"] = revenue

        _update_if_value(
            target,
            "other_non_cash_items",
            report.get("Other Non Cash Items"),
        )
        
        target["period_type"] = period_type

    return list(merged_by_date.values())


def process_yfinance_financials(financials: dict, ticker: str) -> List[dict]:
    if not financials:
        return []

    # 1. Process Annuals
    annual_reports = (
        financials.get("incomeStatement", [])
        + financials.get("balanceSheet", [])
        + financials.get("cashFlow", [])
    )
    annual_records = _process_yfinance_set(annual_reports, "A")
    # Sort Annuals by date for Ratio lookup
    annual_records.sort(key=lambda x: x.get("report_date") or "")

    # Pre-calculate Annual Maintenance CapEx Ratios (CapEx / Revenue)
    # List of (date_str, ratio_float)
    annual_ratios = []
    for rec in annual_records:
        rec["ticker"] = ticker
        rec["data_source"] = "yfinance"
        rec["last_updated"] = None
        
        # Calculate Ratio
        rev = rec.get("total_revenue")
        capex = rec.get("capital_expenditures")
        if rev is not None and capex is not None and rev != 0:
            ratio = abs(capex) / rev
            annual_ratios.append((rec.get("report_date"), ratio))
    
    # 2. Process Quarterlies
    quarterly_reports = (
        financials.get("quarterlyIncomeStatement", [])
        + financials.get("quarterlyBalanceSheet", [])
        + financials.get("quarterlyCashFlow", [])
        + financials.get("quarterlyCashflow", []) # Safety net
    )
    quarterly_records = _process_yfinance_set(quarterly_reports, "Q")
    
    # Sort Quarterlies just in case
    quarterly_records.sort(key=lambda x: x.get("report_date") or "")

    for rec in quarterly_records:
        rec["ticker"] = ticker
        rec["data_source"] = "yfinance"
        rec["last_updated"] = None
        
        # --- REIT PROXY LOGIC ---
        # If CapEx is missing in Quarterly, try to proxy from latest Annual Ratio
        if rec.get("capital_expenditures") is None:
            q_date = rec.get("report_date")
            q_rev = rec.get("total_revenue")
            
            if q_date and q_rev is not None:
                # Find latest annual date strictly BEFORE quarterly date
                best_ratio = None
                # annual_ratios is sorted ascending. Iterate reverse.
                for a_date, a_ratio in reversed(annual_ratios):
                    if a_date and a_date < q_date:
                        best_ratio = a_ratio
                        break
                
                if best_ratio is not None:
                    # Proxy CapEx = Revenue * Ratio
                    proxy_capex = abs(q_rev * best_ratio)
                    rec["capital_expenditures"] = int(proxy_capex) # Store as integer

    # 3. Calculate Free Cash Flow for ALL records (Annual & Quarterly)
    # Formula: FCF = CFO - CapEx (Standard)
    # Strict Null Handling: If any component is None, FCF is None.
    
    all_records = annual_records + quarterly_records
    for rec in all_records:
        cfo = rec.get("cash_flow_from_operations")
        capex = rec.get("capital_expenditures") # Might be proxied above
        sbc = rec.get("stock_based_compensation")
        
        # Standard FCF (used as default)
        if cfo is not None and capex is not None:
            rec["free_cash_flow"] = cfo - abs(capex)
        else:
            rec["free_cash_flow"] = None

        # Insurance proxies for YFinance which lacks strict GAAP tags
        if rec.get("premiums_earned") is None and rec.get("total_revenue") is not None:
             rec["premiums_earned"] = rec.get("total_revenue")
        
        if rec.get("losses_incurred") is None and "cost_of_revenue" in rec:
             rec["losses_incurred"] = rec.get("cost_of_revenue")
             
    return all_records


def merge_financial_records(
    primary_records: List[dict], secondary_records: List[dict], ticker: str
) -> List[dict]:
    # Separate Annuals and Quarterlies
    p_annuals = [r for r in primary_records if r.get("period_type") == "A"]
    s_annuals = [r for r in secondary_records if r.get("period_type") == "A"]
    
    # Existing Annual Merge Logic (Key by Year)
    final_map_annual = {rec["report_date"][:4]: rec for rec in s_annuals}

    for p_rec in p_annuals:
        year = p_rec["report_date"][:4]
        if year in final_map_annual:
            for key, value in p_rec.items():
                if value is not None:
                    final_map_annual[year][key] = value
        else:
            final_map_annual[year] = p_rec

    final_annuals = list(final_map_annual.values())

    # Passthrough for Quarterlies (Key by Report Date + Period Type)
    # Since Finnhub (Primary) is usually Annual-only in this setup, 
    # we just take Secondary (yfinance) Quarterlies.
    # If Primary eventually has Quarterlies, we'd need merge logic here too.
    p_quarters = [r for r in primary_records if r.get("period_type") == "Q"]
    s_quarters = [r for r in secondary_records if r.get("period_type") == "Q"]
    
    # Simple merge for quarters: overwrite secondary with primary if date matches
    # (assuming primary is better quality if present)
    final_map_quarter = {rec["report_date"]: rec for rec in s_quarters}
    for p_rec in p_quarters:
        rd = p_rec["report_date"]
        if rd in final_map_quarter:
            for key, value in p_rec.items():
                if value is not None:
                    final_map_quarter[rd][key] = value
        else:
            final_map_quarter[rd] = p_rec
            
    final_quarters = list(final_map_quarter.values())
    
    # Combine
    all_final = final_annuals + final_quarters

    for record in all_final:
        # Determine source label
        # (Simplified logic: if came from merge map, check if present in original lists)
        # For annuals, relying on year match. For quarters, date match.
        
        # This part is largely for metadata; precise attribution is tricky after merge.
        # We'll default to "Merged" if logic implies it, or keep existing source.
        if record.get("data_source") is None:
             record["data_source"] = "Merged" # Fallback

        # Normalize buyback metrics and compute average price when possible
        shares_val = record.get("shares_repurchased")
        cost_val = record.get("total_cost_of_buybacks")
        avg_price_val = record.get("avg_buyback_price")

        try:
            shares_val = float(shares_val) if shares_val is not None else None
        except Exception:
            shares_val = None
        try:
            cost_val = abs(float(cost_val)) if cost_val is not None else None
        except Exception:
            cost_val = None
        try:
            avg_price_val = float(avg_price_val) if avg_price_val is not None else None
        except Exception:
            avg_price_val = None

        if shares_val is not None:
            record["shares_repurchased"] = shares_val
        if cost_val is not None:
            record["total_cost_of_buybacks"] = cost_val
        if avg_price_val is None and cost_val is not None and shares_val:
            try:
                avg_price_val = cost_val / shares_val if shares_val != 0 else None
            except Exception:
                avg_price_val = None
        if avg_price_val is not None:
            record["avg_buyback_price"] = avg_price_val

        record["ticker"] = ticker
        # Ensure period_type is set (should be from above)
        if not record.get("period_type"):
             record["period_type"] = "A" # Default fallback
             
    return all_final


def extract_fund_metrics(yfinance_info: dict, records: list[dict]) -> list[dict]:
    """Extract fund-specific metrics from yfinance Ticker.info and stamp onto the
    most recent Annual record. These fields feed the True Quantitative scoring.

    Strategy (matching Buffett analysis cadence):
    - We use single-period static values from yfinance.info (not time-series)
    - expense_ratio, dividend_yield, nav_price → taken direct from info (single snapshot)
    - ytd_return, 3yr, 5yr average return → taken from info (annualized % from provider)
    - These are stored only on the most recent Annual record (period_type == 'A').
    """
    if not yfinance_info or not records:
        return records

    def _safe_float(val):
        try:
            return float(val) if val is not None else None
        except (TypeError, ValueError):
            return None

    expense_ratio   = _safe_float(yfinance_info.get("annualReportExpenseRatio"))
    nav_price       = _safe_float(yfinance_info.get("navPrice"))
    dividend_yield  = (
        _safe_float(yfinance_info.get("yield"))
        or _safe_float(yfinance_info.get("dividendYield"))
        or _safe_float(yfinance_info.get("trailingAnnualDividendYield"))
    )
    ytd_return        = _safe_float(yfinance_info.get("ytdReturn"))
    three_year_return = _safe_float(yfinance_info.get("threeYearAverageReturn"))
    five_year_return  = _safe_float(yfinance_info.get("fiveYearAverageReturn"))

    # No fund metrics available — nothing to inject
    if all(v is None for v in [expense_ratio, nav_price, dividend_yield, ytd_return, three_year_return, five_year_return]):
        return records

    # Stamp onto the most recent Annual record
    annual_records = [r for r in records if r.get("period_type") == "A"]
    annual_records.sort(key=lambda r: r.get("report_date") or "", reverse=True)

    if annual_records:
        target = annual_records[0]
        if expense_ratio   is not None: target["expense_ratio"]    = expense_ratio
        if nav_price       is not None: target["nav_price"]         = nav_price
        if dividend_yield  is not None: target["dividend_yield"]    = dividend_yield
        if ytd_return      is not None: target["ytd_return"]        = ytd_return
        if three_year_return is not None: target["three_year_return"] = three_year_return
        if five_year_return  is not None: target["five_year_return"]  = five_year_return
        print(
            f"[FundMetrics] expense_ratio={expense_ratio}, nav={nav_price}, "
            f"yield={dividend_yield}, ytd={ytd_return}, "
            f"3yr={three_year_return}, 5yr={five_year_return}"
        )

    return records
