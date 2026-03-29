# d:\stock-analysis-app\backend\src\jobs\daily_analysis_job.py

import json, os, re
import numpy as np
import pandas as pd
from datetime import datetime, timezone, timedelta
from pathlib import Path
from sqlalchemy import select, update, func, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from backend.src.analysis_engine.valuation import dr_engine
from backend.src.analysis_engine.valuation.valuation_models import (
    _calculate_growth_from_series,
)
from backend.src.analysis_engine.qualitative import (
    process_filing,
    QualitativeAnalysisError,
)
from backend.src.analysis_engine.ai_client import gemini_summarize
from backend.src.jobs.helpers import get_financial_concept, safe_sum, to_int
from backend.src.jobs.financial_processing import (
    process_finnhub_financials,
    process_yfinance_financials,
    merge_financial_records,
    extract_fund_metrics,
)
from backend.src.jobs.db_ops import (
    save_stock_profile,
    upsert_financial_records,
    enforce_data_retention,
    set_system_status,  # <-- added
)
# REMOVED: from backend.src.jobs.market_share_job import upsert_ai_segment_revenues
from backend.src.jobs.analysis_runner import (
    run_quantitative_analysis,
    run_qualitative_analysis,
)
from backend.src.jobs.results_writer import (
    upsert_analysis_result,
    save_document_summary,
)

from backend.src.api_clients.finnhub_client import FinnhubClient
from backend.src.api_clients.sec_client import SecClient
from backend.src.api_clients.yfinance_client import YFinanceClient
from backend.src.database.db_connector import DatabaseConnector
from backend.src.analysis_engine.quantitative import QuantitativeAnalyzer

# Table definitions are centralized in backend.src.database.models
from backend.src.database.models import (
    metadata,
    stocks,
    sec_filings_metadata,
    financial_data,
    stock_analysis_results,
    document_summaries,
)

# Helper functions `get_financial_concept`, `safe_sum`, and `to_int` are
# imported from `backend.src.jobs.helpers` at the top of this file.


RAW_FINANCIAL_TAGS_DIR = (
    Path(__file__).resolve().parents[2] / "data" / "raw_financial_tags"
)

CRITICAL_FINANCIAL_FIELDS = [
    "total_revenue",
    "net_income",
    "gross_profit",
    "total_assets",
    "total_liabilities",
    "share_outstanding_diluted",
    "interest_bearing_debt",
    "interest_expense",
    "cash_and_equivalents",
    "goodwill_and_intangibles",
    "selling_general_and_admin_expense",
    "property_plant_and_equipment_net",
    "accounts_receivable",
    "inventory",
    "accounts_payable",
    "stock_based_compensation",
    "deferred_income_tax",
    "other_non_cash_items",
    "current_assets",
    "current_liabilities",
    "premiums_earned",
    "losses_incurred",
    "dividends_paid",
    "depreciation_and_amortization",
    "operating_income",
    "income_tax_expense",
    "cash_flow_from_operations",
    "capital_expenditures",
    "affo",
    "ffo",
]

AI_METRIC_ALIASES = {
    "revenue": "total_revenue",
    "total_sales": "total_revenue",
    "sales": "total_revenue",
    "net_earnings": "net_income",
    "net_profit": "net_income",
    "gross_margin": "gross_profit",
    "total_assets": "total_assets",
    "total_liabilities": "total_liabilities",
    "shares_outstanding": "share_outstanding_diluted",
    "diluted_shares": "share_outstanding_diluted",
    "long_term_debt": "interest_bearing_debt",
    "debt": "interest_bearing_debt",
    "cash": "cash_and_equivalents",
    "cash_equivalents": "cash_and_equivalents",
    "operating_expenses": "selling_general_and_admin_expense",
    "sg_and_a": "selling_general_and_admin_expense",
    "depreciation": "depreciation_and_amortization",
    "amortization": "depreciation_and_amortization",
    "receivables": "accounts_receivable",
    "inventory": "inventory",
    "payables": "accounts_payable",
    "stock_based_compensation": "stock_based_compensation",
    "share_based_compensation": "stock_based_compensation",
    "deferred_tax": "deferred_income_tax",
    "current_assets": "current_assets",
    "current_liabilities": "current_liabilities",
    "dividends": "dividends_paid",
    "operating_income": "operating_income",
    "income_tax": "income_tax_expense",
    "tax_provision": "income_tax_expense",
    "operating_cash_flow": "cash_flow_from_operations",
    "cfo": "cash_flow_from_operations",
    "capital_expenditures": "capital_expenditures",
    "capex": "capital_expenditures",
    "affo": "affo",
    "adjusted_funds_from_operations": "affo",
    "ffo": "ffo",
    "funds_from_operations": "ffo",
}

FINANCIAL_BACKFILL_YEARS = 3


class DailyAnalysisJob:
    def __init__(self, ticker):
        self.ticker = ticker.upper()
        print(f"--- Starting analysis job for: {self.ticker} ---")
        self.finnhub_client = FinnhubClient()
        self.yfinance_client = YFinanceClient()
        self.sec_client = SecClient()
        self.db_connector = DatabaseConnector()
        self.db_engine = self.db_connector.get_engine()
        self.raw_tags_dir = RAW_FINANCIAL_TAGS_DIR
        self._ai_analysis_cache: dict[str, tuple[dict, str]] = {}

        # --- SMART EARLY SKIP: compare DB vs external sources (SEC-first) ---
        force_rerun_env = os.getenv("FORCE_RERUN", "").strip().lower() in (
            "1",
            "true",
            "yes",
        )
        if force_rerun_env:
            print(
                f"ENV OVERRIDE: FORCE_RERUN set -> will run analysis for {self.ticker} regardless of freshness checks."
            )
            self._should_run = True
            return

        try:
            # Fetch lightweight DB state first (no external API calls)
            with self.db_engine.connect() as conn:
                # last analysis timestamp (stock_analysis_results.analysis_date)
                last_analysis_dt = conn.execute(
                    select(func.max(stock_analysis_results.c.analysis_date)).where(
                        stock_analysis_results.c.ticker == self.ticker
                    )
                ).scalar()

                # latest 10-K filing date known in DB -- SEC-first check
                latest_filing_date = conn.execute(
                    select(func.max(sec_filings_metadata.c.filing_date)).where(
                        sec_filings_metadata.c.ticker == self.ticker,
                        sec_filings_metadata.c.form_type.in_(["10-K", "N-CSR", "N-CSRS"]),
                    )
                ).scalar()

            # --------------------
            #  Gate 0: Annual Cooldown
            # Prefer filing_date-based cooldown: if latest 10-K + 360 days is still in the future,
            # fall back to last analysis timestamp only when filing data is unavailable.
            # --------------------
            try:
                cooldown_deadline = None
                cooldown_source = None
                if latest_filing_date is not None:
                    cooldown_deadline = latest_filing_date + timedelta(days=360)
                    cooldown_source = "filing_date"
                elif last_analysis_dt is not None:
                    last_analysis_date = (
                        last_analysis_dt
                        if isinstance(last_analysis_dt, datetime)
                        else datetime.fromisoformat(str(last_analysis_dt))
                    )
                    cooldown_deadline = last_analysis_date.date() + timedelta(days=360)
                    cooldown_source = "analysis_date"

                if cooldown_deadline is not None:
                    today_utc = datetime.now(timezone.utc).date()
                    if today_utc < cooldown_deadline:
                        days_remaining = (cooldown_deadline - today_utc).days
                        source_msg = (
                            f"latest filing on {latest_filing_date}"
                            if cooldown_source == "filing_date"
                            else f"last analysis on {last_analysis_dt}"
                        )
                        print(
                            f"Gate0: Cooldown active for {self.ticker} based on {source_msg}. "
                            f"{days_remaining} day(s) remaining before full analysis is allowed."
                        )
                        # Defensive local import to avoid module cycles
                        try:
                            from backend.src.jobs.weekly_refresh_job import (
                                perform_weekly_price_refresh,
                            )

                            # Call weekly refresh (will write system_status keys)
                            try:
                                perform_weekly_price_refresh(
                                    self.db_engine,
                                    self.ticker,
                                    min_age_hours=24,
                                    staleness_days=7,
                                    force=False,
                                )
                            except Exception as wr_err:
                                print(
                                    f"Warning: weekly price refresh failed for {self.ticker}: {wr_err}"
                                )
                        except Exception:
                            print(
                                "Warning: weekly_refresh_job not available; skipping lightweight price refresh."
                            )
                        # Persist concise skip info for auditing
                        try:
                            next_full_analysis = cooldown_deadline.isoformat()
                            set_system_status(
                                self.db_engine,
                                f"status:{self.ticker}",
                                {
                                    "phase": "standard",
                                    "ticker": self.ticker,
                                    "status": "skipped",
                                    "reason": "cooldown_360",
                                    "cooldown_source": cooldown_source,
                                    "latest_filing_date": (
                                        latest_filing_date.isoformat()
                                        if latest_filing_date
                                        else None
                                    ),
                                    "last_analysis_date": (
                                        last_analysis_dt.isoformat()
                                        if isinstance(last_analysis_dt, datetime)
                                        else str(last_analysis_dt)
                                        if last_analysis_dt
                                        else None
                                    ),
                                    "next_full_analysis_after": next_full_analysis,
                                    "checked_at": datetime.now(
                                        timezone.utc
                                    ).isoformat(),
                                },
                            )
                        except Exception:
                            pass
                        self._should_run = False
                        return
            except Exception:
                # If any error evaluating Gate0, fall through to normal freshness checks (safer)
                print(
                    f"Warning: failed evaluating Gate0 cooldown for {self.ticker}; continuing freshness checks."
                )

            # If we reach here: either never analyzed before (allow initial run) OR cooldown expired
            # Continue with the rest of the freshness checks (SEC-first)...
            # ...existing code continues (yfinance/finnhub checks and remaining freshness logic)...
        except Exception as e:
            # On any DB/api error, prefer to run (safer) but log diagnostics
            print(
                f"Warning: freshness checks failed for {self.ticker} (error: {e}). Defaulting to run."
            )
            self._should_run = True

    def run_full_analysis(self):
        # Respect early-skip decision
        if not getattr(self, "_should_run", True):
            print(
                f"Job aborted early for {self.ticker}: marked to skip due to recent analysis."
            )
            return

        try:
            profile, yfinance_info = self._fetch_company_profile()
            if not profile:
                return
            self.profile = profile
            self._yfinance_info = yfinance_info

            # --- GATE: Missing Classification ---
            # Check if sector or industry is missing. If so, we cannot proceed with valuation.
            _sector = (profile.get("sector") or "").strip()
            _industry = (profile.get("industry") or "").strip()
            
            if not _sector or not _industry:
                print(f"[Missing Data] {self.ticker} is missing Sector or Industry data. Skipping all analysis.")
                missing_reason = (
                    "ขออภัย ไม่สามารถวิเคราะห์หุ้นตัวนี้ได้เนื่องจากข้อมูลกลุ่มอุตสาหกรรม (Sector/Industry) "
                    "ไม่สมบูรณ์ ทำให้ไม่สามารถเลือกโมเดลการประเมินมูลค่าที่เหมาะสมได้"
                )
                # Save minimal profile so it appears in the system
                self._save_stock_profile(profile, yfinance_info=yfinance_info)
                try:
                    upsert_analysis_result(
                        self.db_engine,
                        stock_analysis_results,
                        {
                            "ticker": self.ticker,
                            "intrinsic_value_estimate": 0.0,
                            "intrinsic_value_reason": missing_reason,
                            "model_used": "missing_data",
                            "analysis_date": datetime.now(timezone.utc),
                        },
                    )
                except Exception as _e:
                    print(f"Warning: Could not save missing data result for {self.ticker}: {_e}")
                print(f"--- Missing Data block applied for {self.ticker}. ---")
                return

            # --- EARLY EXIT: Shell Companies ---
            # Check immediately after profile fetch to avoid wasting any resources
            _industry_upper = _industry.upper()
            _summary  = (yfinance_info.get("longBusinessSummary") or "" if yfinance_info else "").upper()
            if _industry_upper == "SHELL COMPANIES" or "BLANK CHECK" in _summary or "SHELL COMPANY" in _summary:
                print(f"[Shell Company] {self.ticker} is classified as a Shell Company. Skipping all analysis.")
                shell_reason = (
                    "ไม่วิเคราะห์หุ้นกลุ่มนี้ เนื่องจากเป็น Shell Company (Blank Check Company) "
                    "ซึ่งไม่มีการดำเนินงานธุรกิจจริง ไม่มีรายได้ ไม่มีกระแสเงินสด "
                    "และไม่สามารถประเมินมูลค่าที่แท้จริงด้วยวิธีใดได้"
                )
                # Save minimal profile to DB so frontend can display it
                self._save_stock_profile(profile, yfinance_info=yfinance_info)
                # Write a clear analysis result card so the frontend knows why
                try:
                    upsert_analysis_result(
                        self.db_engine,
                        stock_analysis_results,
                        {
                            "ticker": self.ticker,
                            "intrinsic_value_estimate": 0.0,
                            "intrinsic_value_reason": shell_reason,
                            "model_used": "shell_company",
                            "analysis_date": datetime.now(timezone.utc),
                        },
                    )
                except Exception as _e:
                    print(f"Warning: Could not save shell company result for {self.ticker}: {_e}")
                print(f"--- Shell Company block applied for {self.ticker}. No further analysis. ---")
                return

            cik = self.sec_client.get_cik_by_ticker(self.ticker)
            self._save_stock_profile(profile, yfinance_info=yfinance_info)
            should_continue = self._fetch_and_save_financials()
            if not should_continue:
                print(
                    f"Gate requirement not met for {self.ticker}; skipping remaining analysis steps."
                )
                self._record_gate_skip()
                return
            self._fetch_and_save_sec_filings(cik)
            self._enrich_missing_financials()
            self._run_quantitative_analysis()
            self._run_qualitative_analysis(profile=profile, yfinance_info=yfinance_info)
            print(
                f"\n--- Full analysis job for {self.ticker} completed successfully! ---"
            )
        except Exception as e:
            print(
                f"An unexpected error occurred during the analysis for {self.ticker}: {e}"
            )

    def _execute_statement(self, stmt):
        with self.db_engine.connect() as conn:
            conn.execute(stmt)
            conn.commit()

    def _fetch_stock_logo(self, ticker):
        """Fetch stock logo URL from free public endpoint."""
        # We'll use the same logic as fetch_logos.py but simplified for one ticker
        import httpx
        url = f"https://financialmodelingprep.com/image-stock/{ticker.upper()}.png"
        try:
            with httpx.Client(timeout=5, follow_redirects=True) as client:
                resp = client.head(url)
                if resp.status_code == 200 and "image" in resp.headers.get("content-type", ""):
                    return url
        except Exception as e:
            print(f"Warning: could not fetch logo for {ticker}: {e}")
        return None

    def _fetch_company_profile(self):
        try:
            info = self.yfinance_client.get_company_info(self.ticker) or {}
        except Exception as err:
            print(f"Error fetching yfinance company info for {self.ticker}: {err}")
            return None, {}

        if not info:
            print(f"No company info returned by yfinance for {self.ticker}.")
            return None, {}

        logo_url = self._fetch_stock_logo(self.ticker)

        profile = {
            "ticker": self.ticker,
            "company_name": info.get("longName")
            or info.get("shortName")
            or info.get("displayName")
            or self.ticker,
            "market_cap": info.get("marketCap") or info.get("market_cap"),
            "sector": info.get("sector"),
            "industry": info.get("industry"),
            "logo_url": logo_url,
        }

        print(f"Successfully fetched yfinance profile for {profile['company_name']}.")
        return profile, info

    def _write_raw_financial_snapshot(
        self,
        source_name: str,
        payload,
        captured_at: datetime | None = None,
    ) -> None:
        """Persist raw financial payloads to disk for later tag inspection."""

        timestamp = captured_at or datetime.now(timezone.utc)
        safe_ts = timestamp.strftime("%Y%m%dT%H%M%S%fZ")
        try:
            target_dir = (self.raw_tags_dir / self.ticker.upper()).resolve()
            target_dir.mkdir(parents=True, exist_ok=True)
            file_path = target_dir / f"{safe_ts}_{source_name.lower()}.txt"

            formatted_body = self._format_financial_payload(
                source_name, payload, timestamp
            )
            file_path.write_text(formatted_body, encoding="utf-8")
            print(
                f"[RawTag] Saved {source_name} snapshot for {self.ticker} -> {file_path}"
            )
        except Exception as err:
            print(
                f"Warning: could not persist raw {source_name} payload for {self.ticker}: {err}"
            )

    def _format_financial_payload(
        self, source_name: str, payload, captured_at: datetime
    ) -> str:
        header = [
            f"Ticker: {self.ticker.upper()}",
            f"Source: {source_name}",
            f"CapturedAtUTC: {captured_at.isoformat()}",
            "",
        ]

        source = source_name.lower()
        if source == "finnhub":
            body = self._format_finnhub_payload(payload)
        elif source == "yfinance":
            body = self._format_yfinance_payload(payload)
        else:
            try:
                body = [json.dumps(payload, ensure_ascii=False, indent=2, default=str)]
            except Exception:
                body = [str(payload)]

        return "\n".join(header + body) + "\n"

    def _format_finnhub_payload(self, payload) -> list[str]:
        lines: list[str] = []
        data = []
        try:
            data = (payload or {}).get("data", [])
        except AttributeError:
            data = []

        if not data:
            return ["[Data] No items found from Finnhub in this round."]

        # 🔸 หา "ปีล่าสุด" จากทุก report ก่อน
        latest_year = None
        for report in data:
            try:
                endd = report.get("endDate")
                if endd:
                    y = int(str(endd)[:4])
                    if latest_year is None or y > latest_year:
                        latest_year = y
            except Exception:
                continue

        allowed_years: set[int] = set()
        if latest_year is not None:
            allowed_years.add(int(latest_year))
            if latest_year > 0:
                allowed_years.add(int(latest_year - 1))

        # 🔸 กรองเฉพาะรายงานของปีล่าสุดและปีก่อนหน้า
        if latest_year is not None:
            filtered_reports = []
            for r in data:
                try:
                    year_val = int(str(r.get("endDate", ""))[:4])
                except Exception:
                    year_val = None
                if year_val is not None and year_val in allowed_years:
                    filtered_reports.append(r)
            data = filtered_reports

        years_display = (
            ", ".join(str(y) for y in sorted(allowed_years, reverse=True))
            if allowed_years
            else "N/A"
        )
        lines.append(f"[Finnhub] Showing reports for years: {years_display}")

        for idx, report in enumerate(data, start=1):
            end_date = report.get("endDate") if isinstance(report, dict) else None
            form = report.get("form") if isinstance(report, dict) else None
            filed = report.get("filedDate") if isinstance(report, dict) else None
            lines.append(
                f"[Report #{idx}] endDate={end_date or 'N/A'} | form={form or 'N/A'} | filedDate={filed or 'N/A'}"
            )

            report_obj = report.get("report") if isinstance(report, dict) else None
            if not isinstance(report_obj, dict):
                try:
                    lines.append(
                        "  raw_report="
                        + json.dumps(report_obj, ensure_ascii=False, default=str)
                    )
                except Exception:
                    lines.append(f"  raw_report={report_obj}")
                continue

            for stmt_key in sorted(report_obj.keys()):
                items = report_obj.get(stmt_key) or []
                lines.append(
                    f"  Statement: {stmt_key} (items={len(items) if items else 0})"
                )
                if not items:
                    continue
                for item in items:
                    if not isinstance(item, dict):
                        lines.append(f"    raw_item={item}")
                        continue
                    concept = item.get("concept") or "-"
                    label = item.get("label") or "-"
                    unit = item.get("unit") or "-"
                    value = item.get("value")
                    lines.append(
                        f"    concept={concept} | label={label} | value={value} | unit={unit}"
                    )
        return lines

    def _format_yfinance_payload(self, payload) -> list[str]:
        if not isinstance(payload, dict) or not payload:
            return ["[Data] No items found from yfinance in this round."]

        lines: list[str] = []
        # Persist only the most recent two fiscal years discovered across all sections.
        all_sections: dict[str, list[dict]] = {}
        year_candidates: set[int] = set()
        for section, rows in payload.items():
            rows_list = rows if isinstance(rows, list) else []
            all_sections[section] = rows_list
            for row in rows_list:
                if not isinstance(row, dict):
                    continue
                date_val = (
                    row.get("date") or row.get("report_date") or row.get("endDate")
                )
                if not date_val:
                    continue
                try:
                    year = int(str(date_val)[:4])
                except Exception:
                    continue
                year_candidates.add(year)

        sorted_years = sorted(year_candidates, reverse=True)
        allowed_years: set[int] = set(sorted_years[:2])

        years_display = (
            ", ".join(str(y) for y in sorted(allowed_years, reverse=True))
            if allowed_years
            else "N/A"
        )
        lines.append(f"[yfinance] Showing rows for years: {years_display}")

        for section, rows_list in all_sections.items():
            # Filter rows to only include the latest year and the prior year when available
            if allowed_years:
                filtered = []
                for row in rows_list:
                    if not isinstance(row, dict):
                        continue
                    date_val = (
                        row.get("date") or row.get("report_date") or row.get("endDate")
                    )
                    try:
                        year = int(str(date_val)[:4]) if date_val else None
                    except Exception:
                        year = None
                    if year is not None and year in allowed_years:
                        filtered.append(row)
                    elif year is None:
                        continue
            else:
                filtered = rows_list

            lines.append(
                f"[Section] {section} (records={len(filtered) if filtered else 0})"
            )
            if not filtered:
                continue
            for row in filtered:
                try:
                    row_text = json.dumps(row, ensure_ascii=False, default=str)
                except Exception:
                    row_text = str(row)
                lines.append(f"    {row_text}")
        return lines

    def _save_stock_profile(self, profile, yfinance_info=None):
        info = yfinance_info or {}

        sector_value = info.get("sector") or profile.get("sector")
        industry_value = info.get("industry") or profile.get("industry")
        market_cap_raw = (
            profile.get("market_cap")
            or info.get("marketCap")
            or info.get("market_cap")
        )
        market_cap_int = None
        if market_cap_raw is not None:
            try:
                market_cap_int = int(float(market_cap_raw))
            except Exception:
                market_cap_int = None

        stock_data = {
            "ticker": profile.get("ticker"),
            "company_name": profile.get("company_name") or profile.get("name"),
            "sector": sector_value,
            "industry": industry_value or None,
            "market_cap": market_cap_int,
            "logo_url": profile.get("logo_url"),
            "last_updated": datetime.now(timezone.utc),
        }

        try:
            print(f"Upserting stock profile for {self.ticker}...")
            stock_data["last_updated"] = datetime.now(timezone.utc)
            ok = save_stock_profile(self.db_engine, stocks, stock_data)
            if ok:
                print("Stock profile saved successfully.")
            else:
                print(f"Warning: save_stock_profile returned False for {self.ticker}")
        except Exception as e:
            print(f"Error saving stock profile for {self.ticker}: {e}")

    def _fetch_and_save_financials(self):
        finnhub_records = []
        yfinance_records = []

        finnhub_financials = None
        try:
            print("Fetching financials from Finnhub (Primary Source)...")
            finnhub_financials = self.finnhub_client.get_financials_as_reported(
                self.ticker, freq="annual"
            )
        except Exception as fh_err:
            print(
                f"Error fetching financials from Finnhub for {self.ticker}: {fh_err}"
            )

        if finnhub_financials:
            self._write_raw_financial_snapshot("finnhub", finnhub_financials)
            finnhub_records = process_finnhub_financials(
                finnhub_financials, self.ticker
            )

        # Always fetch yfinance to get Quarterlies (Finnhub is Annual-only here)
        # and to fallback for Annuals if Finnhub missing.
        try:
            print("Fetching financials from yfinance (Secondary/Quarterly Source)...")
            yfinance_financials = self.yfinance_client.get_financial_statements(
                self.ticker
            )
            self._write_raw_financial_snapshot("yfinance", yfinance_financials)
            yfinance_records = process_yfinance_financials(
                yfinance_financials, self.ticker
            )
        except Exception as yf_err:
            print(
                f"Error fetching financials from yfinance for {self.ticker}: {yf_err}"
            )

        merged_records = merge_financial_records(
            finnhub_records, yfinance_records, self.ticker
        )

        # For Funds/ETFs: inject expense_ratio, nav_price, yield, returns from yfinance.info
        profile = getattr(self, "_yfinance_info", None) or {}
        industry = (profile.get("industry") or "").upper()
        quote_type = (profile.get("quoteType") or "").upper()
        _is_fund = (
            "FUND" in industry or "ETF" in industry
            or "EXCHANGE TRADED" in industry
            or "ETF" in quote_type
        )
        if _is_fund:
            if not merged_records:
                # Create a synthetic annual record so we can store the fund metrics
                from datetime import datetime, timezone
                merged_records = [{
                    "ticker": self.ticker,
                    "report_date": datetime.now(timezone.utc).date(),
                    "period_type": "A",
                    "total_revenue": 0.0,
                    "net_income": 0.0,
                    "cash_flow_from_operations": 0.0,
                    "data_source": "yfinance_fund",
                    "currency": "USD",
                }]
            merged_records = extract_fund_metrics(profile, merged_records)

        gate_result = self._evaluate_financial_gate(merged_records)
        self._latest_gate_result = gate_result
        summary_message = gate_result.get("summary")
        if summary_message:
            print(summary_message)
        for detail_note in gate_result.get("notes", []):
            print(f"    {detail_note}")

        if merged_records:
            try:
                # Filter strictly for valid columns
                valid_columns = financial_data.columns.keys()
                records_to_save = []
                for record in merged_records:
                    filtered_rec = {
                        key: record.get(key)
                        for key in valid_columns
                        if key != "financial_data_id"
                    }
                    records_to_save.append(filtered_rec)

                print(
                    f"Saving {len(records_to_save)} financial records (Annual + Quarterly) to DB..."
                )
                inserted_count = upsert_financial_records(
                    self.db_engine, financial_data, records_to_save
                )
                print(f"Inserted {inserted_count} new financial records.")

                deleted = enforce_data_retention(
                    self.db_engine, financial_data, self.ticker
                )
                print(f"Retention policy applied. Deleted {deleted} old records.")

            except Exception as e:
                print(f"Error saving financial data: {e}")
        else:
            print(f"No financial records available for {self.ticker}.")

        return gate_result.get("passed", False)

    def _evaluate_financial_gate(self, records):
        """
        Evaluate whether the ticker clears the preliminary financial health gate.
        New Logic (Single Gate):
        Pass if (Avg 3Y CFO > 0) OR (Avg 3Y Net Income > 0).
        """
        profile = getattr(self, "_yfinance_info", None) or getattr(self, "profile", {}) or {}
        industry = (profile.get("industry") or "").upper()
        quote_type = (profile.get("quoteType") or "").upper()
        is_fund = (
            "FUND" in industry or "ETF" in industry
            or "EXCHANGE TRADED" in industry
            or "ETF" in quote_type
        )
        if is_fund:
            return {"passed": True, "passes": 1, "summary": "[Gate] Skipped financial health gate for Funds/ETFs.", "notes": []}
        if not records:
            reason = (
                "[Gate] Skipped analysis because no financial statements found for preliminary evaluation."
            )
            return {
                "passed": False,
                "passes": 0,
                "metrics": {},
                "summary": reason,
                "reason": reason,
                "notes": [],
            }

        # Deduplicate by year
        year_records = []
        seen_years = set()
        for rec in records:
            report_date = rec.get("report_date")
            if not report_date:
                continue
            year_str = str(report_date)[:4]
            if not year_str.isdigit():
                continue
            year = int(year_str)
            if year in seen_years:
                continue
            year_records.append((year, rec))
            seen_years.add(year)

        if not year_records:
            reason = (
                "[Gate] Skipped analysis because financial statement years could not be determined."
            )
            return {
                "passed": False,
                "passes": 0,
                "metrics": {},
                "summary": reason,
                "reason": reason,
                "notes": [],
            }

        # Sort by year descending to get most recent first
        year_records.sort(key=lambda item: item[0], reverse=True)
        
        # Take up to 3 most recent years
        recent_records = year_records[:3]
        years_used = [r[0] for r in recent_records]
        
        cfo_values = []
        ni_values = []
        
        for _, rec in recent_records:
            cfo = self._coerce_numeric(rec.get("cash_flow_from_operations"))
            ni = self._coerce_numeric(rec.get("net_income"))
            
            if cfo is not None:
                cfo_values.append(cfo)
            if ni is not None:
                ni_values.append(ni)

        avg_cfo = float(np.mean(cfo_values)) if cfo_values else 0.0
        avg_ni = float(np.mean(ni_values)) if ni_values else 0.0

        passes_cfo = avg_cfo > 0
        passes_ni = avg_ni > 0
        
        passed = passes_cfo or passes_ni
        
        metrics = {
            "avg_3y_cfo": avg_cfo,
            "avg_3y_net_income": avg_ni,
            "years_analyzed": years_used,
            "passes_cfo": passes_cfo,
            "passes_ni": passes_ni
        }
        
        summary = (
            f"[Gate] Result: {'PASSED' if passed else 'FAILED'}. "
            f"Avg 3Y CFO: ${avg_cfo:,.2f} (>0? {passes_cfo}), "
            f"Avg 3Y Net Income: ${avg_ni:,.2f} (>0? {passes_ni}). "
            f"Years: {years_used}"
        )

        if passed:
            return {
                "passed": True,
                "passes": 1,
                "metrics": metrics,
                "summary": summary,
                "reason": "",
                "notes": [summary],
            }
        else:
            return {
                "passed": False,
                "passes": 0,
                "metrics": metrics,
                "summary": summary,
                "reason": summary,
                "notes": [summary],
            }

    def _record_gate_skip(self):
        """Persist a skip reason when the gate fails so downstream consumers see it."""
        gate_result = getattr(self, "_latest_gate_result", None)
        if not gate_result or gate_result.get("passed"):
            return
        reason = gate_result.get("reason") or "Skipped analysis because preliminary screening criteria were not met."
        payload = {
            "ticker": self.ticker,
            "intrinsic_value_reason": reason,
            "analysis_date": datetime.now(timezone.utc),
        }
        try:
            upsert_analysis_result(self.db_engine, stock_analysis_results, payload)
        except Exception as err:
            print(
                f"Warning: failed to record gate skip reason for {self.ticker}: {err}"
            )

    # data retention now lives in backend/src/jobs/db_ops.py

    def _merge_financial_data(self, primary_records, secondary_records):
        """Thin wrapper kept for compatibility; delegates to the centralized merge helper."""
        return merge_financial_records(primary_records, secondary_records, self.ticker)

    def _process_yfinance_data(self, financials):
        """Backward-compatible thin wrapper that delegates to the centralized helper."""
        return process_yfinance_financials(financials, self.ticker)

    def _fetch_and_save_sec_filings(self, cik):
        if not cik:
            return
        submissions = self.sec_client.get_company_submissions(cik)
        if not submissions or "filings" not in submissions:
            return
        recent_filings = submissions["filings"]["recent"]
        filings_to_save = []
        for i in range(len(recent_filings["form"])):
            form_type = recent_filings["form"][i]
            # Store annual reports and fund shareholder reports; exclude 10-Q
            if form_type in ["10-K", "N-CSR", "N-CSRS"]:
                accession_number = recent_filings["accessionNumber"][i].replace("-", "")
                primary_document = recent_filings["primaryDocument"][i]
                sec_url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession_number}/{primary_document}"
                import uuid
                raw_report_date = recent_filings.get("reportDate", [])[i] if "reportDate" in recent_filings else None
                report_date = raw_report_date if raw_report_date else None
                filings_to_save.append(
                    {
                        "filing_id": str(uuid.uuid4()),
                        "ticker": self.ticker,
                        "form_type": form_type,
                        "filing_date": recent_filings["filingDate"][i],
                        "report_date": report_date,
                        "sec_url": sec_url,
                    }
                )
        if filings_to_save:
            try:
                print(f"Saving {len(filings_to_save)} SEC filing metadata records...")
                stmt = pg_insert(sec_filings_metadata).values(filings_to_save)
                stmt = stmt.on_conflict_do_nothing(index_elements=["sec_url"])
                self._execute_statement(stmt)
                print("SEC filing metadata saved successfully.")
            except Exception as e:
                print(f"Error saving SEC filing metadata: {e}")

    def _enrich_missing_financials(self):
        # AI fallback for missing critical financial metrics has been disabled.
        return

    def _detect_missing_financial_fields(self):
        with self.db_engine.connect() as conn:
            rows = (
                conn.execute(
                    select(financial_data)
                    .where(
                        financial_data.c.ticker == self.ticker,
                        financial_data.c.period_type == "A",
                    )
                    .order_by(financial_data.c.report_date.desc())
                )
                .mappings()
                .all()
            )

        if not rows:
            return []

        entries = []
        seen_years: set[int] = set()
        for row in rows:
            report_date = row.get("report_date")
            if not report_date:
                continue
            try:
                year = report_date.year
            except AttributeError:
                year = int(str(report_date)[:4]) if str(report_date) else None
            if year is None or year in seen_years:
                continue
            missing_fields = []
            for field in CRITICAL_FINANCIAL_FIELDS:
                value = row.get(field)
                if value is None or (isinstance(value, float) and pd.isna(value)):
                    missing_fields.append(field)
            if missing_fields:
                entries.append(
                    {
                        "year": year,
                        "report_date": report_date,
                        "missing_fields": missing_fields,
                    }
                )
            seen_years.add(year)
        return entries


    def _fill_missing_with_ai(self, entries):
        filings_map = self._load_filing_map()
        if not filings_map:
            print(f"No SEC filings available to drive AI backfill for {self.ticker}.")
            return []

        updates = []
        metrics_cache: dict[int, dict[str, float]] = {}

        # Always anchor the AI extraction on the latest 10-K to reuse across steps
        latest_year = max(filings_map.keys())
        latest_filing = filings_map.get(latest_year)
        if not latest_filing:
            return []

        analysis, _ = self._get_or_run_ai_analysis(latest_filing)
        metrics_lookup = self._collect_ai_metrics(analysis)
        for yr, payload in metrics_lookup.items():
            metrics_cache[yr] = payload

        for entry in entries:
            metrics_by_year = metrics_cache.get(entry["year"])
            if not metrics_by_year:
                continue

            update_fields = {
                field: metrics_by_year[field]
                for field in entry["missing_fields"]
                if metrics_by_year.get(field) is not None
            }
            if update_fields:
                updates.append(
                    {
                        "report_date": entry["report_date"],
                        "values": update_fields,
                    }
                )
        if updates:
            print(f"AI extracted {len(updates)} update(s) for {self.ticker}.")
        return updates

    def _apply_financial_updates(self, updates, source_label="manual"):
        if not updates:
            return
        timestamp = datetime.now(timezone.utc)
        try:
            with self.db_engine.connect() as conn:
                with conn.begin():
                    for update_payload in updates:
                        update_values = dict(update_payload["values"])
                        update_values["last_updated"] = timestamp
                        stmt = (
                            update(financial_data)
                            .where(
                                financial_data.c.ticker == self.ticker,
                                financial_data.c.report_date
                                == update_payload["report_date"],
                                financial_data.c.period_type == "A",
                            )
                            .values(**update_values)
                        )
                        conn.execute(stmt)
            print(
                f"Applied {len(updates)} financial update(s) for {self.ticker} using {source_label}."
            )
        except Exception as update_err:
            print(
                f"Warning: failed applying financial updates for {self.ticker}: {update_err}"
            )

    def _load_filing_map(self):
        with self.db_engine.connect() as conn:
            rows = (
                conn.execute(
                    select(
                        sec_filings_metadata.c.filing_id,
                        sec_filings_metadata.c.report_date,
                        sec_filings_metadata.c.sec_url,
                    )
                    .where(
                        sec_filings_metadata.c.ticker == self.ticker,
                        sec_filings_metadata.c.form_type.in_(["10-K", "N-CSR", "N-CSRS"]),
                    )
                    .order_by(sec_filings_metadata.c.report_date.desc())
                )
                .mappings()
                .all()
            )

        filings_map = {}
        for row in rows:
            report_date = row.get("report_date")
            if not report_date:
                continue
            try:
                year = report_date.year
            except AttributeError:
                year = int(str(report_date)[:4]) if str(report_date) else None
            if year is None:
                continue
            filings_map[year] = {
                "filing_id": row.get("filing_id"),
                "report_date": report_date,
                "sec_url": row.get("sec_url"),
            }
        return filings_map

    def _pick_filing_for_year(self, filings_map, year):
        if year in filings_map:
            return filings_map[year]
        if not filings_map:
            return None
        sorted_years = sorted(filings_map.keys())
        candidate = None
        for yr in sorted_years:
            if yr <= year:
                candidate = filings_map[yr]
        if candidate:
            return candidate
        return filings_map[sorted_years[-1]]

    def _get_or_run_ai_analysis(self, filing):
        filing_id_raw = filing.get("filing_id")
        filing_id = str(filing_id_raw)
        cached = self._ai_analysis_cache.get(filing_id)
        if cached:
            return cached

        # Try loading existing summary from document_summaries to avoid rerunning AI
        db_summary = None
        try:
            with self.db_engine.connect() as conn:
                row = conn.execute(
                    select(document_summaries.c.gemini_summary_json).where(
                        document_summaries.c.filing_id == filing_id_raw
                    )
                ).first()
            if row:
                raw_summary = (
                    row._mapping["gemini_summary_json"]
                    if hasattr(row, "_mapping")
                    else row[0]
                )
                if isinstance(raw_summary, str):
                    try:
                        db_summary = json.loads(raw_summary)
                    except json.JSONDecodeError:
                        db_summary = None
                elif isinstance(raw_summary, dict):
                    db_summary = raw_summary
        except Exception as db_err:
            print(
                f"Warning: failed to read cached qualitative summary for filing {filing_id}: {db_err}"
            )

        if db_summary is not None:
            result = (db_summary, "")
            self._ai_analysis_cache[filing_id] = result
            return result

        try:
            result = process_filing(filing_id, filing["sec_url"])
            self._ai_analysis_cache[filing_id] = result
            return result
        except QualitativeAnalysisError as qe:
            print(
                f"Qualitative extraction failed for {self.ticker} filing {filing_id}: {qe}"
            )
            return {}, ""
        except Exception as err:
            print(
                f"Unexpected error during AI extraction for {self.ticker} filing {filing_id}: {err}"
            )
            return {}, ""

    def _collect_ai_metrics(self, final_json):
        # Define aliases locally to prevent scope issues
        AI_METRIC_ALIASES = {
            "revenue": "total_revenue",
            "total_sales": "total_revenue",
            "sales": "total_revenue",
            "net_earnings": "net_income",
            "net_profit": "net_income",
            "gross_margin": "gross_profit",
            "total_assets": "total_assets",
            "total_liabilities": "total_liabilities",
            "shares_outstanding": "share_outstanding_diluted",
            "diluted_shares": "share_outstanding_diluted",
            "long_term_debt": "interest_bearing_debt",
            "debt": "interest_bearing_debt",
            "cash": "cash_and_equivalents",
            "cash_equivalents": "cash_and_equivalents",
            "operating_expenses": "selling_general_and_admin_expense",
            "sg_and_a": "selling_general_and_admin_expense",
            "depreciation": "depreciation_and_amortization",
            "amortization": "depreciation_and_amortization",
            "receivables": "accounts_receivable",
            "inventory": "inventory",
            "payables": "accounts_payable",
            "stock_based_compensation": "stock_based_compensation",
            "share_based_compensation": "stock_based_compensation",
            "deferred_tax": "deferred_income_tax",
            "current_assets": "current_assets",
            "current_liabilities": "current_liabilities",
            "dividends": "dividends_paid",
            "operating_income": "operating_income",
            "income_tax": "income_tax_expense",
            "tax_provision": "income_tax_expense",
            "operating_cash_flow": "cash_flow_from_operations",
            "cfo": "cash_flow_from_operations",
            "capital_expenditures": "capital_expenditures",
            "capex": "capital_expenditures",
        }

        metrics_by_year: dict[int, dict[str, float]] = {}
        if not isinstance(final_json, dict):
            return metrics_by_year
        extracts = final_json.get("financial_extracts") or {}
        metrics_block = extracts.get("critical_financial_metrics")
        if isinstance(metrics_block, dict):
            items = metrics_block.get("value") or []
        elif isinstance(metrics_block, list):
            items = metrics_block
        else:
            items = []

        for item in items:
            if not isinstance(item, dict):
                continue
            metric_name_raw = (item.get("metric") or item.get("name") or "").strip()
            if not metric_name_raw:
                continue
            normalized_key = re.sub(r"[^a-z0-9]+", "_", metric_name_raw.lower()).strip("_")
            metric_key = AI_METRIC_ALIASES.get(normalized_key, normalized_key)
            if metric_key not in CRITICAL_FINANCIAL_FIELDS:
                continue
            fiscal_year = item.get("fiscal_year") or item.get("year")
            try:
                fiscal_year = int(fiscal_year)
            except Exception:
                continue
            raw_value = (
                item.get("value_usd")
                or item.get("value")
                or item.get("numeric_value")
            )
            value = self._coerce_numeric(raw_value)
            if value is None:
                continue
            metrics_by_year.setdefault(fiscal_year, {})[metric_key] = value
        return metrics_by_year

    def _coerce_numeric(self, value):
        if value is None:
            return None
        if isinstance(value, (int, float)):
            if isinstance(value, float) and pd.isna(value):
                return None
            return float(value)
        if isinstance(value, str):
            sanitized = value.strip().lower().replace(",", "")
            sanitized = sanitized.replace("$", "")
            if sanitized.endswith("usd"):
                sanitized = sanitized[:-3]
            multiplier = 1.0
            if sanitized.endswith("%"):
                sanitized = sanitized[:-1]
                multiplier = 0.01
            if sanitized.endswith("x"):
                sanitized = sanitized[:-1]
            try:
                return float(sanitized) * multiplier
            except Exception:
                return None
        return None

    def _run_quantitative_analysis(self):
        print("\n--- Starting Quantitative Analysis ---")
        try:
            with self.db_engine.connect() as conn:
                stmt = select(financial_data).where(
                    financial_data.c.ticker == self.ticker
                )
                result_proxy = conn.execute(stmt)
                financial_records = [dict(row) for row in result_proxy.mappings()]

            if not financial_records:
                print(f"No financial data in DB for {self.ticker} to analyze.")
                return

            # Split into Annual and Quarterly
            annuals = [r for r in financial_records if r.get("period_type") == "A"]
            quarterlies = [r for r in financial_records if r.get("period_type") == "Q"]

            records_to_update = []

            # 1. Process Annuals
            if annuals:
                print(f"Running Quantitative Analyzer on {len(annuals)} Annual records...")
                analyzer_a = QuantitativeAnalyzer(annuals)
                metrics_a = analyzer_a.calculate_metrics()
                if not metrics_a.empty:
                    metrics_a = metrics_a.where(pd.notna(metrics_a), None)
                    # Add period_type explicitly to match DB key
                    metrics_a["period_type"] = "A"
                    records_to_update.extend(metrics_a.to_dict(orient="records"))

            # 2. Process Quarterlies
            if quarterlies:
                print(f"Running Quantitative Analyzer on {len(quarterlies)} Quarterly records...")
                analyzer_q = QuantitativeAnalyzer(quarterlies)
                metrics_q = analyzer_q.calculate_metrics()
                if not metrics_q.empty:
                    metrics_q = metrics_q.where(pd.notna(metrics_q), None)
                    metrics_q["period_type"] = "Q"
                    records_to_update.extend(metrics_q.to_dict(orient="records"))

            if not records_to_update:
                print("Quantitative analyzer returned no metrics.")
                return

            print(
                f"Updating {len(records_to_update)} records with new calculated metrics..."
            )
            with self.db_engine.connect() as conn:
                with conn.begin():  # Use a transaction for efficiency
                    for record in records_to_update:
                        # Explicitly convert any remaining pandas/numpy NaN-like values to None
                        update_values = {
                            key: (None if pd.isna(value) else value)
                            for key, value in record.items()
                            if key not in ("report_date", "period_type")
                        }

                        stmt = (
                            update(financial_data)
                            .where(
                                financial_data.c.ticker == self.ticker,
                                financial_data.c.report_date
                                == record["report_date"].date(),
                                financial_data.c.period_type == record["period_type"],
                            )
                            .values(**update_values)
                        )
                        conn.execute(stmt)
            print("Quantitative analysis and DB update complete.")
        except Exception as e:
            print(f"An error occurred during quantitative analysis: {e}")
            # Re-raise the exception to let the main runner know this critical step failed
            raise e

    def _run_qualitative_analysis(self, profile: dict = None, yfinance_info: dict = None):
        """
        Runs qualitative analysis using a single, consolidated API call that
        fetches both the summary and key financial figures like depreciation.
        """
        print("\n--- Starting Consolidated Qualitative Analysis ---")
        try:
            with self.db_engine.connect() as conn:
                # ค้นหาเอกสาร 10-K ล่าสุด (เหมือนเดิม)
                stmt = (
                    select(
                        sec_filings_metadata.c.filing_id,
                        sec_filings_metadata.c.sec_url,
                        sec_filings_metadata.c.report_date,
                    )
                    .where(
                        sec_filings_metadata.c.ticker == self.ticker,
                        sec_filings_metadata.c.form_type.in_(["10-K", "N-CSR", "N-CSRS"]),
                    )
                    .order_by(sec_filings_metadata.c.filing_date.desc())
                    .limit(1)
                )
                latest_filing = conn.execute(stmt).first()

            if not latest_filing:
                is_fund = False
                
                if yfinance_info:
                    quote_type = (yfinance_info.get("quoteType") or "").upper()
                    if quote_type in ["MUTUALFUND", "ETF"]:
                        is_fund = True
                        
                ind_sec = ""
                if profile:
                    ind_sec += (profile.get("industry") or "").upper() + " "
                    ind_sec += (profile.get("sector") or "").upper() + " "
                    ind_sec += (profile.get("company_name") or "").upper() + " "
                if yfinance_info:
                    ind_sec += (yfinance_info.get("industry") or "").upper() + " "
                    ind_sec += (yfinance_info.get("sector") or "").upper() + " "
                    ind_sec += (yfinance_info.get("longName") or "").upper() + " "
                    ind_sec += (yfinance_info.get("shortName") or "").upper() + " "
                    summary = (yfinance_info.get("longBusinessSummary") or "").upper()
                    # Check first 250 chars of summary for fund keywords
                    ind_sec += summary[:250] + " "
                    
                if "FUND" in ind_sec or "ETF" in ind_sec or "EXCHANGE TRADED" in ind_sec or "CLOSED END" in ind_sec:
                    is_fund = True
                
                if is_fund:
                    print(f"No 10-K pattern found, but {self.ticker} is a Fund/ETF. Using yfinance Profile for qualitative analysis.")
                    from backend.src.analysis_engine.qualitative import process_fund_profile
                    import uuid
                    summary_text = "No business summary available."
                    if yfinance_info and yfinance_info.get("longBusinessSummary"):
                        summary_text = yfinance_info.get("longBusinessSummary")
                    
                    dummy_filing_id = None
                    
                    try:
                        with self.db_engine.connect() as conn:
                            # First, check if a FUND-PROFILE row already exists for this ticker
                            existing = conn.execute(
                                select(sec_filings_metadata.c.filing_id)
                                .where(
                                    sec_filings_metadata.c.ticker == self.ticker,
                                    sec_filings_metadata.c.form_type == "FUND-PROFILE"
                                )
                                .limit(1)
                            ).first()
                            if existing:
                                dummy_filing_id = str(existing.filing_id)
                                print(f"Reusing existing virtual SEC filing {dummy_filing_id} for {self.ticker}.")
                            else:
                                import uuid as _uuid
                                dummy_filing_id = str(_uuid.uuid4())
                                with conn.begin():
                                    conn.execute(pg_insert(sec_filings_metadata).values({
                                        "filing_id": dummy_filing_id,
                                        "ticker": self.ticker,
                                        "form_type": "FUND-PROFILE",
                                        "filing_date": datetime.now(timezone.utc).date(),
                                        "report_date": datetime.now(timezone.utc).date(),
                                        "sec_url": f"virtual://fund-profile/{self.ticker}"
                                    }).on_conflict_do_nothing())
                                print(f"Created virtual SEC filing {dummy_filing_id} for {self.ticker}.")
                    except Exception as e:
                        print(f"Warning: Failed to create virtual SEC filing for {self.ticker}: {e}")
                        return
                        
                    try:
                        analysis_data, _ = process_fund_profile(dummy_filing_id, summary_text)
                        print(f"Fund qualitative analysis complete for {self.ticker}.")
                        return
                    except Exception as e:
                        import traceback
                        print(f"Fund qualitative analysis failed for {self.ticker}: {e}")
                        traceback.print_exc()
                        return
                        
                print(f"No 10-K filing found in DB for {self.ticker}.")
                return

            print(
                f"Found latest 10-K. Filing ID: {latest_filing.filing_id} for report date: {latest_filing.report_date}"
            )

            # --- Step 1: Run consolidated analysis using the single, powerful prompt ---
            # analysis_data ที่ได้กลับมา จะมีข้อมูลครบถ้วนทั้ง summary และ financial_extracts
            filing_payload = {
                "filing_id": latest_filing.filing_id,
                "sec_url": latest_filing.sec_url,
            }
            try:
                analysis_data, cleaned_text = self._get_or_run_ai_analysis(
                    filing_payload
                )
            except Exception as e:
                import traceback

                print(
                    f"An unexpected error occurred during qualitative analysis for {self.ticker}: {e}"
                )
                traceback.print_exc()
                raise
            if not analysis_data:
                raise QualitativeAnalysisError(
                    f"AI analysis failed to return structured data for {self.ticker}."
                )

            # Persist document summary JSON (AI raw output) for later inspection
            try:
                save_document_summary(
                    self.db_connector.get_engine(),
                    document_summaries,
                    latest_filing.filing_id,
                    analysis_data.get("gemini_summary_json") or analysis_data,
                )
                print("Document summary saved to DB.")
                
                # --- REMOVED: AI-derived segment revenues persistence ---
                # The call to upsert_ai_segment_revenues has been removed as requested.
                
            except Exception as e:
                print(
                    f"Warning: failed to save document summary for {self.ticker}: {e}"
                )

            # NOTE:
            # We intentionally do NOT upsert the raw AI `analysis_data` into
            # `stock_analysis_results` here. The full analysis (which includes
            # quantitative + qualitative + valuation) will assemble a final
            # `final_result` and the unified runner will persist that as the
            # authoritative row. Writing the raw AI output early causes column
            # shifts and overwritten/null fields in the final table.
            print(
                "Intermediate qualitative analysis complete; document summary persisted. Will not upsert partial AI result into stock_analysis_results."
            )

            # --- Step 2: Extract depreciation data from the consolidated result ---
            # (DISABLED per user request to stop AI from overwriting primary financial data)
            # extracts = analysis_data.get("financial_extracts", {})
            # ... depreciation extraction logic removed ...
            
            # Helper: scale numeric value by unit string into absolute integer
            def _scale_value_to_int(numeric_val, unit_str):
                try:
                    if numeric_val is None:
                        return None
                    scaled = float(numeric_val)
                except Exception:
                    return None
                u = (unit_str or "").lower() if unit_str else ""
                if "trillion" in u or u.endswith("t") or "t" == u:
                    scaled *= 1_000_000_000_000
                elif "billion" in u or u.endswith("b") or "b" == u:
                    scaled *= 1_000_000_000
                elif "million" in u or u.endswith("m") or "m" == u:
                    scaled *= 1_000_000
                elif "thousand" in u or u.endswith("k") or "k" == u:
                    scaled *= 1_000
                # If unit is plain 'usd' or unspecified, assume value already absolute
                return int(round(scaled))

            def _parse_numeric_value(raw):
                if raw is None:
                    return None
                if isinstance(raw, (int, float)):
                    return float(raw)
                if isinstance(raw, str):
                    cleaned = raw.replace(",", " ").strip().lower()
                    match = re.search(r"-?\d+(?:\.\d+)?", cleaned)
                    if match:
                        try:
                            return float(match.group())
                        except Exception:
                            return None
                return None

            def _scale_numeric_value(numeric_val, unit_str):
                base = _parse_numeric_value(numeric_val)
                if base is None:
                    return None
                unit = (unit_str or "").lower()
                if "trillion" in unit or unit.endswith("t"):
                    base *= 1_000_000_000_000
                elif "billion" in unit or unit.endswith("b"):
                    base *= 1_000_000_000
                elif "million" in unit or unit.endswith("m"):
                    base *= 1_000_000
                elif "thousand" in unit or unit.endswith("k"):
                    base *= 1_000
                return base

            def _ensure_financial_row(report_date_obj):
                if report_date_obj is None:
                    return {}
                try:
                    with self.db_engine.connect() as conn:
                        row = conn.execute(
                            select(
                                financial_data.c.shares_repurchased,
                                financial_data.c.total_cost_of_buybacks,
                                financial_data.c.avg_buyback_price,
                            ).where(
                                financial_data.c.ticker == self.ticker,
                                financial_data.c.report_date == report_date_obj,
                                financial_data.c.period_type == "A",
                            )
                        ).mappings().first()
                        if row:
                            return dict(row)
                        ins_payload = {
                            "ticker": self.ticker,
                            "report_date": report_date_obj,
                            "period_type": "A",
                            "data_source": "AI",
                            "last_updated": datetime.now(timezone.utc),
                        }
                        stmt_ins = pg_insert(financial_data).values(ins_payload)
                        stmt_ins = stmt_ins.on_conflict_do_nothing(
                            index_elements=["ticker", "report_date", "period_type"]
                        )
                        conn.execute(stmt_ins)
                        conn.commit()
                        return {}
                except Exception as ie:
                    print(
                        f"[Extractor] Failed to ensure financial_data row for {self.ticker} {report_date_obj}: {ie}"
                    )
                return {}

            def _is_missing_value(val):
                if val is None:
                    return True
                try:
                    return abs(float(val)) < 1e-9
                except Exception:
                    return False

            # (Depreciation extraction logic removed per user request)

            # --- Buyback metrics extraction (AI fallback when API data is missing) ---
            buyback_section = analysis_data.get("buyback_analysis")
            if not buyback_section:
                fin_extracts = analysis_data.get("financial_extracts", {})
                if isinstance(fin_extracts, dict):
                    buyback_section = (
                        fin_extracts.get("buyback_analysis")
                        or fin_extracts.get("buyback_activity")
                        or fin_extracts.get("buyback_metrics")
                    )

            if isinstance(buyback_section, dict):
                buyback_entries = (
                    buyback_section.get("value")
                    or buyback_section.get("entries")
                    or []
                )
            elif isinstance(buyback_section, list):
                buyback_entries = buyback_section
            else:
                buyback_entries = []

            if buyback_entries:
                for entry in buyback_entries:
                    if not isinstance(entry, dict):
                        continue
                    try:
                        yr = (
                            entry.get("year")
                            or entry.get("fiscal_year")
                            or entry.get("report_year")
                        )
                        rd = entry.get("report_date") or entry.get("report_date_str")

                        shares_info = entry.get("shares_repurchased") or entry.get(
                            "shares_buyback"
                        )
                        cost_info = (
                            entry.get("total_cost_of_buybacks")
                            or entry.get("buyback_cost")
                            or entry.get("total_buyback_cost")
                        )
                        avg_info = (
                            entry.get("avg_buyback_price")
                            or entry.get("average_buyback_price")
                        )

                        shares_unit = ""
                        cost_unit = ""
                        avg_unit = ""

                        if isinstance(shares_info, dict):
                            shares_val_raw = shares_info.get("value")
                            shares_unit = shares_info.get("unit") or ""
                        else:
                            shares_val_raw = shares_info

                        if isinstance(cost_info, dict):
                            cost_val_raw = cost_info.get("value")
                            cost_unit = cost_info.get("unit") or ""
                        else:
                            cost_val_raw = cost_info

                        if isinstance(avg_info, dict):
                            avg_val_raw = avg_info.get("value")
                            avg_unit = avg_info.get("unit") or ""
                        else:
                            avg_val_raw = avg_info

                        shares_scaled = _scale_numeric_value(
                            shares_val_raw, shares_unit
                        )
                        cost_scaled = _scale_numeric_value(cost_val_raw, cost_unit)
                        avg_scaled = _scale_numeric_value(avg_val_raw, avg_unit)

                        if shares_scaled is not None:
                            shares_scaled = abs(shares_scaled)
                        if cost_scaled is not None:
                            cost_scaled = abs(cost_scaled)

                        if avg_scaled is None and shares_scaled and cost_scaled:
                            try:
                                avg_scaled = cost_scaled / shares_scaled
                            except Exception:
                                avg_scaled = None

                        if shares_scaled is None and cost_scaled is None and avg_scaled is None:
                            continue

                        report_date_obj = None
                        if rd:
                            try:
                                if isinstance(rd, str):
                                    try:
                                        parsed = datetime.fromisoformat(rd)
                                        report_date_obj = parsed.date()
                                    except Exception:
                                        report_date_obj = (
                                            datetime.strptime(
                                                rd[:10], "%Y-%m-%d"
                                            ).date()
                                            if "-" in rd
                                            else None
                                        )
                                elif hasattr(rd, "date"):
                                    report_date_obj = (
                                        rd.date() if isinstance(rd, datetime) else rd
                                    )
                            except Exception:
                                report_date_obj = None
                        if report_date_obj is None and yr:
                            try:
                                year_int = int(str(yr)[:4])
                                # Look up existing Annual report date for this year to ensure sync
                                with self.db_engine.connect() as conn:
                                    existing_date = conn.execute(
                                        select(financial_data.c.report_date)
                                        .where(
                                            financial_data.c.ticker == self.ticker,
                                            financial_data.c.period_type == "A",
                                            func.extract("year", financial_data.c.report_date) == year_int
                                        )
                                        .limit(1)
                                    ).scalar()
                                    if existing_date:
                                        report_date_obj = existing_date
                            except Exception as ex:
                                print(f"[Extractor] Error looking up report date for year {yr}: {ex}")
                                report_date_obj = None

                        if report_date_obj is None:
                            print(
                                f"[Extractor] Skipping buyback entry due to missing year/date or no matching Annual record: {entry}"
                            )
                            continue

                        # We only update existing rows found above, so _ensure_financial_row is redundant but harmless if date matches.
                        # However, for safety, let's just proceed to update.
                        # existing_row = _ensure_financial_row(report_date_obj) # _ensure inserts if missing
                        
                        # Fetch current values to check if update is needed (without inserting)
                        existing_row = {}
                        try:
                             with self.db_engine.connect() as conn:
                                row = conn.execute(
                                    select(
                                        financial_data.c.shares_repurchased,
                                        financial_data.c.total_cost_of_buybacks,
                                        financial_data.c.avg_buyback_price,
                                    ).where(
                                        financial_data.c.ticker == self.ticker,
                                        financial_data.c.report_date == report_date_obj,
                                        financial_data.c.period_type == "A",
                                    )
                                ).mappings().first()
                                if row:
                                    existing_row = dict(row)
                        except Exception:
                            pass

                        update_fields = {}
                        if (
                            shares_scaled is not None
                            and _is_missing_value(
                                (existing_row or {}).get("shares_repurchased")
                            )
                        ):
                            update_fields["shares_repurchased"] = float(
                                round(shares_scaled, 4)
                            )
                        if (
                            cost_scaled is not None
                            and _is_missing_value(
                                (existing_row or {}).get("total_cost_of_buybacks")
                            )
                        ):
                            update_fields["total_cost_of_buybacks"] = float(
                                round(cost_scaled, 2)
                            )
                        if (
                            avg_scaled is not None
                            and _is_missing_value(
                                (existing_row or {}).get("avg_buyback_price")
                            )
                        ):
                            update_fields["avg_buyback_price"] = float(
                                round(avg_scaled, 4)
                            )

                        if not update_fields:
                            continue

                        update_fields["last_updated"] = datetime.now(timezone.utc)

                        try:
                            with self.db_engine.connect() as conn:
                                upd = (
                                    update(financial_data)
                                    .where(
                                        financial_data.c.ticker == self.ticker,
                                        financial_data.c.report_date
                                        == report_date_obj,
                                        financial_data.c.period_type == "A",
                                    )
                                    .values(**update_fields)
                                )
                                conn.execute(upd)
                                conn.commit()
                        except Exception as be:
                            print(
                                f"Warning: failed to upsert buyback metrics for {self.ticker} {report_date_obj}: {be}"
                            )
                    except Exception as entry_err:
                        print(
                            f"Warning: error processing buyback entry {entry}: {entry_err}"
                        )
        except QualitativeAnalysisError as e:
            print(f"Qualitative analysis process failed for {self.ticker}: {e}")
            raise e
        except Exception as e:
            print(
                f"An unexpected error occurred during qualitative analysis for {self.ticker}: {e}"
            )
            raise e
