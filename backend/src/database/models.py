"""Centralized SQLAlchemy Table definitions used across jobs and DB ops.

This module extracts the table/schema definitions previously embedded
in `daily_analysis_job.py` so other modules can import them from one place.
"""

from sqlalchemy import (
    Table,
    Column,
    Text,
    BIGINT,
    TIMESTAMP,
    BOOLEAN,
    UUID,
    DATE,
    NUMERIC,
    JSON,
    MetaData,
    ForeignKey,
    UniqueConstraint,
    Integer,
)
from sqlalchemy import func
from sqlalchemy.dialects.postgresql import JSONB

metadata = MetaData()

stocks = Table(
    "stocks",
    metadata,
    Column("ticker", Text, primary_key=True),
    Column("company_name", Text, nullable=False),
    Column("sector", Text),
    Column("industry", Text),
    Column("market_cap", BIGINT),
    Column("logo_url", Text),
    Column(
        "last_updated",
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        server_onupdate=func.now(),
    ),
    Column("is_active", BOOLEAN, default=True),
)

sec_filings_metadata = Table(
    "sec_filings_metadata",
    metadata,
    Column("filing_id", UUID, primary_key=True, server_default=func.uuid_generate_v4()),
    Column("ticker", Text, nullable=False),
    Column("form_type", Text, nullable=False),
    Column("filing_date", DATE, nullable=False),
    Column("report_date", DATE),
    Column("sec_url", Text, nullable=False, unique=True),
)

financial_data = Table(
    "financial_data",
    metadata,
    Column(
        "financial_data_id",
        UUID,
        primary_key=True,
        server_default=func.uuid_generate_v4(),
    ),
    Column("ticker", Text, nullable=False),
    Column("report_date", DATE, nullable=False),
    Column("period_type", Text, nullable=False),
    # --- Base Financial Fields ---
    Column("total_revenue", BIGINT),
    Column("net_income", BIGINT),
    Column("total_assets", BIGINT),
    Column("total_liabilities", BIGINT),
    Column("share_outstanding_diluted", BIGINT),
    Column("shares_repurchased", NUMERIC(20, 4)),
    Column("total_cost_of_buybacks", NUMERIC(20, 2)),
    Column("avg_buyback_price", NUMERIC(15, 4)),
    Column("interest_bearing_debt", BIGINT),
    Column("cash_and_equivalents", BIGINT),
    Column("goodwill_and_intangibles", BIGINT),
    Column("selling_general_and_admin_expense", BIGINT),
    Column("depreciation_and_amortization", BIGINT),
    Column("property_plant_and_equipment_net", BIGINT),
    Column("accounts_receivable", BIGINT),
    Column("inventory", BIGINT),
    Column("accounts_payable", BIGINT),
    Column("current_assets", BIGINT),
    Column("current_liabilities", BIGINT),
    Column("stock_based_compensation", BIGINT),
    Column("deferred_income_tax", BIGINT),
    Column("other_non_cash_items", BIGINT),
    Column("operating_income", BIGINT),
    Column("income_tax_expense", BIGINT),
    Column("cash_flow_from_operations", BIGINT),
    Column("capital_expenditures", BIGINT),
    Column("gross_profit", BIGINT),
    Column("interest_expense", BIGINT),
    Column("premiums_earned", BIGINT),
    Column("losses_incurred", BIGINT),
    Column("dividends_paid", BIGINT),
    # Optional: per-year revenue breakdown by segment (raw JSON from provider)
    # --- Calculated Metrics ---
    Column("roe", NUMERIC(10, 4)),
    Column("roic", NUMERIC(10, 4)),
    Column("debt_to_equity", NUMERIC(10, 4)),
    Column("free_cash_flow", BIGINT),
    Column("eps_diluted", NUMERIC(10, 4)),
    Column("revenue_growth", NUMERIC(10, 4)),
    Column("eps_growth_diluted", NUMERIC(10, 4)),
    Column("fcf_growth", NUMERIC(10, 4)),
    Column("gross_margin", NUMERIC(10, 4)),
    Column("net_profit_margin", NUMERIC(10, 4)),
    Column("fcf_margin", NUMERIC(10, 4)),
    Column("interest_coverage", NUMERIC(10, 4)),
    Column("combined_ratio", NUMERIC(10, 4)),
    Column("payout_ratio", NUMERIC(10, 4)),
    # --- FUND METRICS ---
    Column("expense_ratio", NUMERIC(10, 4)),
    Column("nav_price", NUMERIC(15, 4)),
    Column("dividend_yield", NUMERIC(10, 4)),
    Column("ytd_return", NUMERIC(10, 4)),
    Column("three_year_return", NUMERIC(10, 4)),
    Column("five_year_return", NUMERIC(10, 4)),
    # --- NEW: per-report-year Intrinsic Value estimate (mimics stock_analysis_results.intrinsic_value_estimate)
    Column("intrinsic_value_estimate", NUMERIC(15, 2)),
    Column("data_source", Text, nullable=False),
    Column(
        "last_updated",
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        server_onupdate=func.now(),
    ),
    UniqueConstraint(
        "ticker", 
        "report_date", 
        "period_type", 
        name="financial_data_unique_key"
    ),
)

stock_analysis_results = Table(
    "stock_analysis_results",
    metadata,
    Column(
        "analysis_id", UUID, primary_key=True, server_default=func.uuid_generate_v4()
    ),
    Column("ticker", Text, nullable=False, unique=True),
    Column("analysis_date", TIMESTAMP(timezone=True), default=func.now()),
    Column("moat_rating", Text),
    Column("conviction_score", NUMERIC(5, 2)),
    Column("key_risks", Text),
    Column("intrinsic_value_estimate", NUMERIC(15, 2)),
    Column("intrinsic_value_reason", Text),
    Column("ai_recommendation_summary", Text),
    Column("ai_reasoning", JSONB),
    Column("portfolio_directive", JSONB),
    Column("margin_of_safety", NUMERIC(7, 4)),
    Column("current_price", NUMERIC(15, 4)),
    Column("checklist_details", JSONB),
    Column("model_used", Text),
)

document_summaries = Table(
    "document_summaries",
    metadata,
    Column(
        "filing_id",
        UUID,
        ForeignKey("sec_filings_metadata.filing_id"),
        primary_key=True,
    ),
    Column("gemini_summary_json", JSONB),
    Column("ai_model", Text),
    Column(
        "last_updated",
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        server_onupdate=func.now(),
    ),
)

# Split tables: product segments and geography segments (optional use).
product_segment_revenues = Table(
    "product_segment_revenues",
    metadata,
    Column(
        "segment_revenue_id",
        UUID,
        primary_key=True,
        server_default=func.uuid_generate_v4(),
    ),
    Column("ticker", Text, nullable=False),
    Column("report_date", DATE, nullable=False),
    Column("period_type", Text, nullable=False),
    Column("segment_original_name", Text, nullable=False),
    Column("segment_group", Text, nullable=False),
    Column("revenue_amount", BIGINT),
    Column("revenue_amount_raw", NUMERIC(20, 6)),
    Column("revenue_unit", Text),
    Column("ai_confidence", NUMERIC(5, 4)),
    Column("revenue_growth_pct", NUMERIC(10, 4)),
    Column("data_source", Text),
    Column(
        "last_updated",
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        server_onupdate=func.now(),
    ),
    UniqueConstraint(
        "ticker",
        "report_date",
        "period_type",
        "segment_group",
        name="product_segment_revenues_unique_key",
    ),
)

geo_segment_revenues = Table(
    "geo_segment_revenues",
    metadata,
    Column(
        "segment_revenue_id",
        UUID,
        primary_key=True,
        server_default=func.uuid_generate_v4(),
    ),
    Column("ticker", Text, nullable=False),
    Column("report_date", DATE, nullable=False),
    Column("period_type", Text, nullable=False),
    Column("segment_original_name", Text, nullable=False),
    Column("segment_group", Text, nullable=False),
    Column("revenue_amount", BIGINT),
    Column("revenue_amount_raw", NUMERIC(20, 6)),
    Column("revenue_unit", Text),
    Column("ai_confidence", NUMERIC(5, 4)),
    Column("revenue_growth_pct", NUMERIC(10, 4)),
    Column("data_source", Text),
    Column(
        "last_updated",
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        server_onupdate=func.now(),
    ),
    UniqueConstraint(
        "ticker",
        "report_date",
        "period_type",
        "segment_group",
        name="geo_segment_revenues_unique_key",
    ),
)

# Lightweight key-value system status store (e.g., pipeline phases)
system_status = Table(
    "system_status",
    metadata,
    Column("key", Text, primary_key=True),
    Column("value", JSONB),
    Column(
        "last_updated",
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        server_onupdate=func.now(),
    ),
)

portfolio_state = Table(
    "portfolio_state",
    metadata,
    Column("state_id", Integer, primary_key=True),
    Column("portfolio_value", NUMERIC(18, 4)),
    Column("portfolio_peak", NUMERIC(18, 4)),
    Column("start_value", NUMERIC(18, 4)),
    Column("start_date", DATE),
    Column("total_days", Integer),
    Column("sum_return", NUMERIC(18, 6)),
    Column("sum_squared_diff", NUMERIC(18, 6)),
    Column("risk_free_rate", NUMERIC(10, 4)),
    Column("sharpe_ratio", NUMERIC(10, 4)),
    Column("cagr", NUMERIC(10, 4)),
    Column("max_drawdown", NUMERIC(10, 4)),
    Column("total_return", NUMERIC(10, 4)),
    Column("last_update", DATE),
    Column(
        "updated_at",
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        server_onupdate=func.now(),
    ),
)

portfolio_checkpoints = Table(
    "portfolio_checkpoints",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("year", Integer, nullable=False),
    Column("month", Integer, nullable=False),
    Column("portfolio_value", NUMERIC(18, 4)),
    Column("cagr", NUMERIC(10, 4)),
    Column("sharpe", NUMERIC(10, 4)),
    Column("drawdown", NUMERIC(10, 4)),
    Column("total_return", NUMERIC(10, 4)),
    Column(
        "created_at",
        TIMESTAMP(timezone=True),
        server_default=func.now(),
    ),
    UniqueConstraint("year", "month", name="portfolio_checkpoints_year_month_key"),
)

transactions = Table(
    "transactions",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("date", DATE, nullable=False),
    Column("ticker", Text),
    Column("type", Text, nullable=False),
    Column("amount", NUMERIC(18, 4)),
    Column("price", NUMERIC(15, 4)),
    Column("quantity", NUMERIC(18, 6)),
    Column("cash_after", NUMERIC(18, 4)),
    Column(
        "created_at",
        TIMESTAMP(timezone=True),
        server_default=func.now(),
    ),
)

portfolio_positions = Table(
    "portfolio_positions",
    metadata,
    Column("ticker", Text, primary_key=True),
    Column("analysis_date", TIMESTAMP(timezone=True)),
    Column("conviction_score", NUMERIC(5, 2)),
    Column("conviction_baseline_score", NUMERIC(5, 2)),
    Column("conviction_baseline_date", DATE),
    Column("conviction_change_pct", NUMERIC(7, 3)),
    Column("margin_of_safety", NUMERIC(7, 4)),
    Column("mos_baseline_value", NUMERIC(7, 4)),
    Column("mos_baseline_date", DATE),
    Column("mos_change_pct", NUMERIC(7, 3)),
    Column("current_price", NUMERIC(15, 4)),
    Column("quantity", NUMERIC(18, 6)),
    Column("cost_basis", NUMERIC(18, 4)),
    Column("current_value", NUMERIC(18, 4)),
    Column("current_pct", NUMERIC(7, 3)),
    Column("target_pct", NUMERIC(7, 3)),
    Column("delta_pct", NUMERIC(7, 3)),
    Column("total_return", NUMERIC(10, 4)),
    Column("action_label", Text),
    Column("action", Text),
    Column("reallocation_flag", BOOLEAN, default=False),
    Column("details", JSONB),
    Column(
        "last_updated",
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        server_onupdate=func.now(),
    ),
)
