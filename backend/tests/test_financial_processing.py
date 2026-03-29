from backend.src.jobs.financial_processing import (
    extract_fund_metrics,
    process_finnhub_financials,
    process_yfinance_financials,
)


def test_process_finnhub_financials_maps_core_fields_and_normalizes_buybacks():
    payload = {
        "data": [
            {
                "endDate": "2024-12-31",
                "report": {
                    "ic": [
                        {"concept": "us-gaap_Revenues", "value": 1000},
                        {"concept": "us-gaap_NetIncomeLoss", "value": 200},
                        {
                            "concept": "us-gaap_RevenueFromContractWithCustomerExcludingAssessedTax",
                            "value": 1000,
                        },
                        {
                            "concept": "us-gaap_CostOfGoodsAndServicesSold",
                            "value": 400,
                        },
                    ],
                    "bs": [
                        {"concept": "us-gaap_Assets", "value": 5000},
                        {"concept": "us-gaap_LiabilitiesCurrent", "value": 900},
                        {"concept": "us-gaap_LiabilitiesNoncurrent", "value": 600},
                        {"concept": "us-gaap_CommercialPaper", "value": 50},
                        {"concept": "us-gaap_LongTermDebtNoncurrent", "value": 250},
                        {
                            "concept": "us-gaap_CashAndCashEquivalentsAtCarryingValue",
                            "value": 700,
                        },
                    ],
                    "cf": [
                        {
                            "concept": "us-gaap_NetCashProvidedByUsedInOperatingActivities",
                            "value": 300,
                        },
                        {
                            "concept": "us-gaap_PaymentsToAcquirePropertyPlantAndEquipment",
                            "value": -80,
                        },
                        {
                            "concept": "us-gaap_PaymentsForRepurchaseOfCommonStock",
                            "value": -120,
                        },
                    ],
                },
            }
        ]
    }

    records = process_finnhub_financials(payload, "TEST")

    assert len(records) == 1
    record = records[0]
    assert record["ticker"] == "TEST"
    assert record["period_type"] == "A"
    assert record["total_revenue"] == 1000
    assert record["gross_profit"] == 600
    assert record["total_liabilities"] == 1500
    assert record["interest_bearing_debt"] == 300
    assert record["cash_and_equivalents"] == 700
    assert record["total_cost_of_buybacks"] == 120


def test_process_yfinance_financials_proxies_quarterly_capex_and_calculates_fcf():
    payload = {
        "incomeStatement": [
            {
                "date": "2023-12-31",
                "Total Revenue": 1000,
                "Net Income": 220,
                "Diluted Average Shares": 100,
            }
        ],
        "balanceSheet": [
            {
                "date": "2023-12-31",
                "Total Assets": 2000,
                "Total Liabilities Net Minority Interest": 900,
            }
        ],
        "cashFlow": [
            {
                "date": "2023-12-31",
                "Cash Flow From Continuing Operating Activities": 400,
                "Capital Expenditure": -100,
            }
        ],
        "quarterlyIncomeStatement": [
            {
                "date": "2024-03-31",
                "Total Revenue": 300,
                "Net Income": 70,
            }
        ],
        "quarterlyCashFlow": [
            {
                "date": "2024-03-31",
                "Cash Flow From Continuing Operating Activities": 120,
            }
        ],
    }

    records = process_yfinance_financials(payload, "QORX")

    annual = next(
        record
        for record in records
        if record["period_type"] == "A" and record["report_date"] == "2023-12-31"
    )
    quarter = next(
        record
        for record in records
        if record["period_type"] == "Q" and record["report_date"] == "2024-03-31"
    )

    assert annual["free_cash_flow"] == 300
    assert quarter["capital_expenditures"] == 30
    assert quarter["free_cash_flow"] == 90
    assert quarter["ticker"] == "QORX"
    assert quarter["data_source"] == "yfinance"


def test_extract_fund_metrics_stamps_latest_annual_record_only():
    records = [
        {"report_date": "2023-12-31", "period_type": "A"},
        {"report_date": "2024-03-31", "period_type": "Q"},
        {"report_date": "2024-12-31", "period_type": "A"},
    ]

    updated = extract_fund_metrics(
        {
            "annualReportExpenseRatio": 0.0045,
            "navPrice": 25.5,
            "yield": 0.018,
            "ytdReturn": 0.06,
            "threeYearAverageReturn": 0.08,
            "fiveYearAverageReturn": 0.1,
        },
        records,
    )

    latest_annual = next(record for record in updated if record["report_date"] == "2024-12-31")
    older_annual = next(record for record in updated if record["report_date"] == "2023-12-31")

    assert latest_annual["expense_ratio"] == 0.0045
    assert latest_annual["nav_price"] == 25.5
    assert latest_annual["dividend_yield"] == 0.018
    assert latest_annual["ytd_return"] == 0.06
    assert latest_annual["three_year_return"] == 0.08
    assert latest_annual["five_year_return"] == 0.1
    assert "expense_ratio" not in older_annual
