"""Thin wrappers to run Quantitative and Qualitative analysis from the orchestrator.
These functions keep `daily_analysis_job.py` concise while reusing the existing analyzer classes.
"""

from backend.src.analysis_engine.quantitative import QuantitativeAnalyzer
from backend.src.analysis_engine.qualitative import (
    process_filing,
    QualitativeAnalysisError,
)
from datetime import datetime, timezone


def run_quantitative_analysis(db_engine, financial_data_table, ticker: str):
    with db_engine.connect() as conn:
        stmt = financial_data_table.select().where(
            financial_data_table.c.ticker == ticker
        )
        result_proxy = conn.execute(stmt)
        financial_records = [dict(row) for row in result_proxy.mappings()]

    if not financial_records:
        return None

    analyzer = QuantitativeAnalyzer(financial_records)
    calculated_metrics_df = analyzer.calculate_metrics()
    if calculated_metrics_df.empty:
        return None

    # Convert NaN to None for DB writes
    calculated_metrics_df = calculated_metrics_df.where(
        calculated_metrics_df.notna(), None
    )
    return calculated_metrics_df.to_dict(orient="records")


def run_qualitative_analysis(
    db_engine, ticker: str, sec_filings_metadata_table, financial_data_table
):
    # Find latest 10-K
    with db_engine.connect() as conn:
        stmt = (
            sec_filings_metadata_table.select()
            .where(
                sec_filings_metadata_table.c.ticker == ticker,
                sec_filings_metadata_table.c.form_type.in_(["10-K", "N-CSR", "N-CSRS"]),
            )
            .order_by(sec_filings_metadata_table.c.filing_date.desc())
            .limit(1)
        )
        latest_filing = conn.execute(stmt).first()

    if not latest_filing:
        return None

    analysis_data, cleaned_text = process_filing(
        latest_filing.filing_id, latest_filing.sec_url
    )

    # Extract depreciation if present
    extracts = analysis_data.get("financial_extracts", {})
    dep_data = extracts.get("depreciation_and_amortization", {}).get("value")
    if dep_data and dep_data.get("value") is not None:
        value = float(dep_data["value"])
        unit = dep_data.get("unit", "").lower()
        scaled_value = value
        if "billion" in unit:
            scaled_value *= 1_000_000_000
        elif "million" in unit:
            scaled_value *= 1_000_000
        return {
            "depreciation_from_10k": int(scaled_value),
            "report_date": latest_filing.report_date,
        }

    return None
