# backend/unified_runner.py
import os
import json
import math
import traceback
import time
import pandas as pd
import numpy as np
from typing import Any, Dict, Optional, List, Tuple
from decimal import Decimal
from sqlalchemy import select, update, insert
from sqlalchemy.dialects.postgresql import insert as pg_insert
from concurrent.futures import ProcessPoolExecutor, as_completed
import multiprocessing
from datetime import datetime, timedelta, timezone
from backend.src.analysis_engine.qualitative import QualitativeAnalysisError
from backend.src.api_clients.sec_client import SecClient

# --- แก้ไข Import ให้ถูกต้องตามโครงสร้างโปรเจกต์ ---
from backend.src.database.db_connector import DatabaseConnector
from backend.src.jobs.db_ops import set_system_status, get_system_status
from backend.src.jobs.triggers import TriggerEvaluator
from backend.src.jobs.daily_analysis_job import DailyAnalysisJob
from backend.src.analysis_engine.investment_checklist import InvestmentChecklistAnalyzer
from backend.src.api_clients.yfinance_client import YFinanceClient

# --- Import Table Definitions ---
from backend.src.jobs.daily_analysis_job import (
    stocks,
    financial_data,
    document_summaries,
    stock_analysis_results,
    sec_filings_metadata,
)


# --- UPGRADED: Universal JSON Sanitizer ---
def sanitize_for_json(obj):
    """
    Recursively traverses a data structure and converts non-serializable
    types (Decimal, numpy types) to their native Python equivalents.
    """
    if isinstance(obj, list):
        return [sanitize_for_json(i) for i in obj]
    if isinstance(obj, tuple):
        return [sanitize_for_json(i) for i in obj]
    if isinstance(obj, dict):
        return {k: sanitize_for_json(v) for k, v in obj.items()}

    if obj is None:
        return None

    # Handle pandas-specific missing values (pd.NA, np.nan, etc.)
    try:
        if pd.isna(obj):
            return None
    except TypeError:
        pass

    # Preserve booleans explicitly (since bool is subclass of int)
    if isinstance(obj, (np.bool_, bool)):
        return bool(obj)

    # Type Conversions
    if isinstance(obj, (np.integer, np.int64, int)):
        return int(obj)

    if isinstance(obj, (Decimal, float, np.floating)):
        val = float(obj)
        # Replace NaN/Inf with None to produce valid JSON payloads
        if math.isnan(val) or math.isinf(val):
            return None
        return val

    return obj


def check_if_recently_analyzed(ticker, engine, days=90):
    """
    ตรวจสอบว่าหุ้นตัวนี้เคยถูกวิเคราะห์แบบละเอียด (มีผลใน stock_analysis_results)
    ในช่วงเวลาที่กำหนดหรือไม่
    """
    ninety_days_ago = datetime.now(timezone.utc) - timedelta(days=days)

    with engine.connect() as conn:
        stmt = (
            select(stock_analysis_results)
            .where(
                stock_analysis_results.c.ticker == ticker,
                stock_analysis_results.c.analysis_date >= ninety_days_ago,
            )
            .limit(1)
        )

        result = conn.execute(stmt).first()
        return result is not None


def _get_latest_db_year_and_updated(ticker: str, engine):
    """Return (latest_year:int|None, latest_last_updated:datetime|None) from DB."""
    from sqlalchemy import func as _func

    with engine.connect() as conn:
        row = conn.execute(
            select(
                _func.max(financial_data.c.report_date),
                _func.max(financial_data.c.last_updated),
            ).where(
                financial_data.c.ticker == ticker,
                financial_data.c.period_type == "A",
            )
        ).first()
    if not row or (row[0] is None and row[1] is None):
        return None, None
    latest_date, latest_updated = row
    return (latest_date.year if latest_date else None, latest_updated)


def _get_last_analysis_date(ticker: str, engine):
    from sqlalchemy import func as _func

    with engine.connect() as conn:
        last_dt = conn.execute(
            select(_func.max(stock_analysis_results.c.analysis_date)).where(
                stock_analysis_results.c.ticker == ticker
            )
        ).scalar()
    return last_dt


def _get_env_int(name: str, default: int) -> int:
    """
    Safely parse environment variable integers without crashing the runner.
    """
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


TERMINAL_SUCCESS_STATUSES = {"success", "gate_skipped"}


def _latest_year_from_external_sources(ticker: str) -> int | None:
    """Return the newest annual report year using Finnhub first with yfinance fallback."""
    years: set[int] = set()

    try:
        from backend.src.api_clients.finnhub_client import FinnhubClient

        fh_client = FinnhubClient()
        fin = fh_client.get_financials_as_reported(ticker, freq="annual")
        for report in (fin or {}).get("data", []) or []:
            end_date = report.get("endDate")
            if not end_date:
                continue
            year_str = str(end_date)[:4]
            if year_str.isdigit():
                years.add(int(year_str))
        if years:
            return max(years)
    except Exception:
        pass

    try:
        yf_client = YFinanceClient()
        fin = yf_client.get_financial_statements(ticker)
        if not fin:
            return None
        for key in ("incomeStatement", "balanceSheet", "cashFlow"):
            for rec in fin.get(key, []) or []:
                d = rec.get("date")
                if not d:
                    continue
                y = str(d)[:4]
                if y.isdigit():
                    years.add(int(y))
        return max(years) if years else None
    except Exception:
        return max(years) if years else None


def _should_force_run_for_new_year(ticker: str, engine) -> bool:
    """
    Force run if:
    - External data (Finnhub primary, yfinance fallback) shows a newer annual year than DB, or
    - DB financials were updated after the last analysis run.
    """
    db_year, db_last_updated = _get_latest_db_year_and_updated(ticker, engine)
    src_year = _latest_year_from_external_sources(ticker)

    has_new_year_available = src_year is not None and (
        db_year is None or src_year > db_year
    )

    last_analysis_dt = _get_last_analysis_date(ticker, engine)
    db_newer_than_analysis = (
        db_last_updated is not None
        and last_analysis_dt is not None
        and db_last_updated > last_analysis_dt
    )

    return bool(has_new_year_available or db_newer_than_analysis)


def _has_valid_intrinsic_value(ticker: str, engine) -> bool:
    with engine.connect() as conn:
        value = conn.execute(
            select(stock_analysis_results.c.intrinsic_value_estimate)
            .where(stock_analysis_results.c.ticker == ticker)
            .limit(1)
        ).scalar_one_or_none()
    try:
        return value is not None and float(value) not in (0.0, 0)
    except (TypeError, ValueError):
        return False


def _evaluate_ticker_for_run(
    ticker: str,
    db_engine,
    trigger_eval: TriggerEvaluator,
    weekly_due: bool,
) -> Optional[Dict[str, Any]]:
    # --- existing pre-checks ---
    # NOTE: Do NOT call yfinance/finnhub here. Freshness / new-year detection
    # is the responsibility of DailyAnalysisJob which follows an SEC-first policy.
    recently = check_if_recently_analyzed(ticker, db_engine)
    status_payload: Dict[str, Any] = {}
    try:
        status_payload = get_system_status(db_engine, f"status:{ticker}") or {}
    except Exception:
        status_payload = {}

    last_status = (status_payload or {}).get("status")
    failure_stage = (status_payload or {}).get("failure_stage")

    # allow operator override to force a rerun even if 'recently' is True
    force_rerun_env = os.getenv("FORCE_RERUN", "").strip().lower() in (
        "1",
        "true",
        "yes",
    )
    if force_rerun_env:
        print(
            f"ENV OVERRIDE: FORCE_RERUN enabled -> will override recent-analysis skip for {ticker} if needed."
        )

    run_reasons: List[str] = []
    latest_filing_date = None

    failed_statuses = {"failed", "failure", "qual_failure", "exception"}
    needs_recovery = False
    if last_status in failed_statuses:
        needs_recovery = True
    elif last_status == "running" and not status_payload.get("finished_at"):
        needs_recovery = True

    if needs_recovery:
        recovery_hint = failure_stage or last_status or "unknown"
        print(
            f"--- FORCING RECOVERY RUN for {ticker}: last_status={last_status} stage={recovery_hint} ---"
        )
        if "recover_failed_run" not in run_reasons:
            run_reasons.append("recover_failed_run")
        recently = False

    filing_due, candidate_date = trigger_eval.has_new_filing(ticker)
    weekly_trigger = weekly_due

    # Keep trigger-based scheduling only; detailed new-year checks are deferred
    # to DailyAnalysisJob (SEC-first + provider sync checks).
    if filing_due:
        run_reasons.append("new_sec_filing")
        latest_filing_date = candidate_date

    if weekly_trigger:
        # Weekly trigger is allowed only if there's an existing intrinsic value or other triggers.
        # _has_valid_intrinsic_value is DB-only and safe here.
        if filing_due:
            run_reasons.append("weekly_price_refresh")
        else:
            if _has_valid_intrinsic_value(ticker, db_engine):
                run_reasons.append("weekly_price_refresh")
            else:
                print(
                    f"--- SKIPPING {ticker}: Weekly refresh requires a valid intrinsic value. ---"
                )
                weekly_trigger = False

    # Provide detailed skip reason and persist status when we decide to skip
    if not run_reasons and recently and not force_rerun_env:
        last_analysis_dt = _get_last_analysis_date(ticker, db_engine)
        db_year, db_last_updated = _get_latest_db_year_and_updated(ticker, db_engine)
        skip_details = {
            "phase": "standard",
            "ticker": ticker,
            "status": "skipped",
            "reason": "recent_analysis",
            "last_analysis_date": (
                last_analysis_dt.isoformat() if last_analysis_dt else None
            ),
            "db_latest_financial_year": db_year,
            "db_latest_financial_last_updated": (
                db_last_updated.isoformat() if db_last_updated else None
            ),
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }
        try:
            # Persist a short-lived system status record to help troubleshooting
            set_system_status(db_engine, f"status:{ticker}", skip_details)
        except Exception:
            # non-fatal: still print diagnostics
            pass

        print(
            f"--- SKIPPING {ticker}: Already analyzed recently (last_analysis={last_analysis_dt}). "
            f"Set FORCE_RERUN=1 to override. Skip details written to system_status key status:{ticker} ---"
        )
        return None

    # If operator forced rerun, mark the reason
    if not run_reasons and recently and force_rerun_env:
        run_reasons.append("forced_by_env")

    if not run_reasons:
        run_reasons.append("initial_run")

    return {
        "ticker": ticker,
        "run_reasons": run_reasons,
        "weekly_trigger": "weekly_price_refresh" in run_reasons and weekly_trigger,
        "latest_filing_date": latest_filing_date,
    }


def _execute_ticker_job(job: Dict[str, Any]) -> Dict[str, Any]:
    ticker = job["ticker"]
    run_reasons = job.get("run_reasons", [])
    weekly_trigger = job.get("weekly_trigger", False)
    latest_filing_date = job.get("latest_filing_date")
    latest_filing_iso = (
        latest_filing_date.isoformat()
        if hasattr(latest_filing_date, "isoformat")
        else str(latest_filing_date)
        if latest_filing_date
        else None
    )

    print("=" * 50)
    print(f"--- PROCESSING TICKER: {ticker} ({', '.join(run_reasons)}) ---")

    db_engine = DatabaseConnector().get_engine()
    api_cache: Dict[str, Any] = {}

    try:
        try:
            started_at = datetime.now(timezone.utc).isoformat()
            set_system_status(
                db_engine,
                f"status:{ticker}",
                {
                    "phase": "standard",
                    "ticker": ticker,
                    "status": "running",
                    "run_reasons": run_reasons,
                    "latest_filing_date": latest_filing_iso,
                    "started_at": started_at,
                },
            )
        except Exception:
            pass

        # --- PRICE-ONLY: Delegate to weekly_refresh_job for clarity and staleness handling ---
        try:
            if weekly_trigger and set(run_reasons) == {"weekly_price_refresh"}:
                from backend.src.jobs.weekly_refresh_job import (
                    perform_weekly_price_refresh,
                )

                print(f"--- PRICE-ONLY: Delegating weekly refresh for {ticker} ---")
                res = perform_weekly_price_refresh(
                    db_engine,
                    ticker,
                    min_age_hours=24,
                    staleness_days=7,
                )
                # perform_weekly_price_refresh returns a dict compatible with unified_runner expectations
                if res:
                    return res
                # If it returns falsy, fall through to full analysis (fallback)
        except Exception as e:
            # Non-fatal: log and continue to full analysis path
            print(
                f"[PRICE-ONLY] Error delegating to weekly_refresh_job for {ticker}: {e}"
            )

        data_collection_job = DailyAnalysisJob(ticker=ticker)
        data_collection_job.run_full_analysis()

        gate_result = getattr(data_collection_job, "_latest_gate_result", None)
        if gate_result and not gate_result.get("passed", True):
            gate_reason = (
                gate_result.get("summary")
                or gate_result.get("reason")
                or "Skipped analysis because preliminary screening criteria were not met."
            )
            print(f"[Gate:{ticker}] {gate_reason}")
            try:
                finished_at = datetime.now(timezone.utc).isoformat()
                status_payload = {
                    "phase": "standard",
                    "ticker": ticker,
                    "status": "gate_skipped",
                    "failure_stage": "financial_gate",
                    "error": gate_reason,
                    "finished_at": finished_at,
                    "run_reasons": run_reasons,
                    "latest_filing_date": latest_filing_iso,
                    "weekly_trigger": bool(weekly_trigger),
                    "gate_result": sanitize_for_json(gate_result),
                }
                set_system_status(db_engine, f"status:{ticker}", status_payload)
            except Exception:
                pass
            return {
                "ticker": ticker,
                "status": "gate_skipped",
                "weekly_trigger": False,
                "latest_filing_date": latest_filing_date,
                "error": gate_reason,
            }

        with db_engine.connect() as conn:
            profile_res = conn.execute(
                select(stocks).where(stocks.c.ticker == ticker)
            ).first()
            profile = dict(profile_res._mapping) if profile_res else {}

            quant_res = conn.execute(
                select(financial_data).where(financial_data.c.ticker == ticker)
            )
            quant_df = pd.DataFrame(quant_res.mappings().all())

            qual_row = conn.execute(
                select(
                    document_summaries.c.gemini_summary_json,
                    document_summaries.c.ai_model,
                )
                .join(
                    sec_filings_metadata,
                    sec_filings_metadata.c.filing_id == document_summaries.c.filing_id,
                )
                .where(sec_filings_metadata.c.ticker == ticker)
                .order_by(sec_filings_metadata.c.filing_date.desc())
            ).first()

        if not qual_row:
            qual_summary = {}
            qual_model_name = None
        else:
            mapping = qual_row._mapping if hasattr(qual_row, "_mapping") else None
            if mapping:
                raw_json = mapping.get("gemini_summary_json")
                qual_model_name = mapping.get("ai_model")
            else:
                raw_json, qual_model_name = qual_row
            if isinstance(raw_json, str):
                qual_summary = json.loads(raw_json)
            elif isinstance(raw_json, dict):
                qual_summary = raw_json
            else:
                qual_summary = {}

        # --- SHELL COMPANY BLOCK ---
        # After loading profile from DB, check again to ensure any ticker that
        # is a Shell Company is immediately skipped without deep analysis.
        _p_industry = (profile.get("industry") or "").upper()
        _p_model = (profile.get("model_used") or "").lower()
        if _p_industry == "SHELL COMPANIES" or _p_model == "shell_company":
            shell_reason = (
                "ไม่วิเคราะห์หุ้นกลุ่มนี้ เนื่องจากเป็น Shell Company "
                "ที่ไม่มีการดำเนินงานธุรกิจจริง ไม่สามารถประเมินมูลค่าได้"
            )
            print(f"[Worker:{ticker}] Shell Company detected at post-pipeline stage. Skipping deep analysis.")
            set_system_status(db_engine, f"status:{ticker}", {
                "phase": "standard",
                "ticker": ticker,
                "status": "shell_company",
                "error": shell_reason,
                "finished_at": datetime.now(timezone.utc).isoformat(),
                "run_reasons": run_reasons,
            })
            return {
                "ticker": ticker,
                "status": "shell_company",
                "weekly_trigger": False,
                "latest_filing_date": latest_filing_iso,
                "error": shell_reason,
            }

        if quant_df.empty or not qual_summary or not profile:
            print(
                f"!!! WARNING: Missing necessary data for {ticker}. Skipping deep analysis. !!!"
            )
            return {
                "ticker": ticker,
                "status": "skipped",
                "weekly_trigger": False,
                "latest_filing_date": None,
                "error": "Missing profile/financials/summary",
            }

        yfinance_client = YFinanceClient()
        from backend.src.api_clients.finnhub_client import FinnhubClient

        finnhub_client = FinnhubClient()
        analyzer = InvestmentChecklistAnalyzer(
            ticker,
            quant_df,
            qual_summary,
            profile,
            yfinance_client,
            finnhub_client,
            shared_cache=api_cache,
        )
        final_result = analyzer.run_full_analysis()

        print("[4/4] Saving comprehensive analysis result to database...")
        final_result_sanitized = sanitize_for_json(final_result)

        with db_engine.connect() as conn:
            with conn.begin():
                existing_record = conn.execute(
                    select(stock_analysis_results.c.ticker).where(
                        stock_analysis_results.c.ticker == ticker
                    )
                ).first()

                update_data = {
                    key: value
                    for key, value in final_result_sanitized.items()
                    if key != "ticker"
                }

                if existing_record:
                    print(f"Updating existing record for {ticker}...")
                    stmt = (
                        update(stock_analysis_results)
                        .where(stock_analysis_results.c.ticker == ticker)
                        .values(**update_data)
                    )
                else:
                    print(f"Inserting new analysis record for {ticker}...")
                    insert_payload = {"ticker": ticker}
                    insert_payload.update(update_data)
                    stmt = insert(stock_analysis_results).values(**insert_payload)

                conn.execute(stmt)

                # --- NEW: Upsert intrinsic_value_estimate into financial_data (per report year) ---
                try:
                    iv = final_result_sanitized.get("intrinsic_value_estimate")
                    if iv is not None:
                        # User Request: Store IV on the latest ANNUAL record (10-K), not 10-Q.
                        target_date = None
                        try:
                            qdf = getattr(analyzer, "quant_df", None)
                            if isinstance(qdf, pd.DataFrame) and not qdf.empty:
                                # Filter for Annuals only
                                annuals = qdf[qdf["period_type"] == "A"]
                                if not annuals.empty:
                                    target_date_raw = annuals["report_date"].max()
                                    # Convert to date object
                                    if isinstance(target_date_raw, pd.Timestamp):
                                        target_date = target_date_raw.date()
                                    elif isinstance(target_date_raw, datetime):
                                        target_date = target_date_raw.date()
                                    elif isinstance(target_date_raw, str):
                                        target_date = datetime.fromisoformat(str(target_date_raw)[:10]).date()
                        except Exception:
                            target_date = None

                        # Fallback: use latest_filing_date if available and we couldn't find it in quant_df
                        if target_date is None and latest_filing_date is not None:
                            try:
                                if isinstance(latest_filing_date, datetime):
                                    target_date = latest_filing_date.date()
                                else:
                                    target_date = latest_filing_date
                            except Exception:
                                target_date = None

                        # Final fallback: use analysis_date year-end
                        if target_date is None:
                            try:
                                ad = final_result_sanitized.get("analysis_date")
                                if ad:
                                    if isinstance(ad, str):
                                        ad_dt = datetime.fromisoformat(ad)
                                    elif isinstance(ad, pd.Timestamp):
                                        ad_dt = ad.to_pydatetime()
                                    elif isinstance(ad, datetime):
                                        ad_dt = ad
                                    else:
                                        ad_dt = None
                                    if ad_dt:
                                        target_date = datetime(
                                            ad_dt.year, 12, 31
                                        ).date()
                            except Exception:
                                target_date = None

                        if target_date is not None:
                            # Update existing row if present, else insert a minimal stub then update
                            try:
                                # Try updating existing row
                                upd = (
                                    update(financial_data)
                                    .where(
                                        financial_data.c.ticker == ticker,
                                        financial_data.c.report_date == target_date,
                                        financial_data.c.period_type == "A",
                                    )
                                    .values(
                                        intrinsic_value_estimate=float(iv),
                                        last_updated=datetime.now(timezone.utc),
                                    )
                                )
                                res = conn.execute(upd)
                                # If nothing updated, insert minimal stub
                                if getattr(res, "rowcount", None) in (0, None):
                                    ins_payload = {
                                        "ticker": ticker,
                                        "report_date": target_date,
                                        "period_type": "A",
                                        "data_source": "analysis",
                                        "intrinsic_value_estimate": float(iv),
                                        "last_updated": datetime.now(timezone.utc),
                                    }
                                    stmt_ins = pg_insert(financial_data).values(
                                        ins_payload
                                    )
                                    stmt_ins = stmt_ins.on_conflict_do_nothing(
                                        index_elements=[
                                            "ticker",
                                            "report_date",
                                            "period_type",
                                        ]
                                    )
                                    conn.execute(stmt_ins)
                                # commit inside transaction block is handled by conn.begin()
                                print(
                                    f"Intrinsic value {iv} persisted for {ticker} report_date={target_date}"
                                )
                            except Exception as upderr:
                                print(
                                    f"Warning: failed to persist intrinsic value for {ticker} {target_date}: {upderr}"
                                )
                    else:
                        print(
                            f"No intrinsic_value_estimate returned for {ticker}; skipping financial_data update."
                        )
                except Exception as e_iv:
                    print(
                        f"Warning: intrinsic value upsert step failed for {ticker}: {e_iv}"
                    )
        try:
            completed_at = datetime.now(timezone.utc).isoformat()
            set_system_status(
                db_engine,
                f"status:{ticker}",
                {
                    "phase": "standard",
                    "ticker": ticker,
                    "status": "completed",
                    "run_reasons": run_reasons,
                    "analysis_date": completed_at,
                    "completed_at": completed_at,
                    "latest_filing_date": latest_filing_iso,
                    "weekly_trigger": bool(weekly_trigger),
                },
            )
        except Exception:
            pass

        return {
            "ticker": ticker,
            "status": "success",
            "weekly_trigger": weekly_trigger,
            "latest_filing_date": latest_filing_date,
        }

    except QualitativeAnalysisError as e:
        print(
            f"!!! SKIPPING {ticker}: Qualitative analysis failed due to AI API issues. ({e}) !!!"
        )
        try:
            finished_at = datetime.now(timezone.utc).isoformat()
            set_system_status(
                db_engine,
                f"status:{ticker}",
                {
                    "phase": "standard",
                    "ticker": ticker,
                    "status": "failed",
                    "failure_stage": "qualitative_analysis",
                    "error": str(e),
                    "finished_at": finished_at,
                    "run_reasons": run_reasons,
                    "latest_filing_date": latest_filing_iso,
                    "weekly_trigger": bool(weekly_trigger),
                },
            )
        except Exception:
            pass
        return {
            "ticker": ticker,
            "status": "qual_failure",
            "weekly_trigger": False,
            "latest_filing_date": None,
            "error": str(e),
        }
    except Exception as e:
        print(
            f"!!! FAILED UNIFIED ANALYSIS FOR {ticker} with an unexpected error: {e} !!!"
        )
        traceback.print_exc()
        try:
            finished_at = datetime.now(timezone.utc).isoformat()
            set_system_status(
                db_engine,
                f"status:{ticker}",
                {
                    "phase": "standard",
                    "ticker": ticker,
                    "status": "failed",
                    "error": str(e),
                    "failure_stage": "execution",
                    "finished_at": finished_at,
                    "run_reasons": run_reasons,
                    "latest_filing_date": latest_filing_iso,
                    "weekly_trigger": bool(weekly_trigger),
                },
            )
        except Exception:
            pass
        return {
            "ticker": ticker,
            "status": "failure",
            "weekly_trigger": False,
            "latest_filing_date": None,
            "error": str(e),
        }


def run_ranking_system(db_engine):
    """
    Fetches all analysis results and ranks them based on a combined score.
    """
    print("\n" + "=" * 20 + " [FINAL STEP] Running Global Ranking System " + "=" * 20)

    with db_engine.connect() as conn:
        # Join with stocks to get current price if not in analysis table
        # For this example, assume intrinsic_value and conviction_score are populated
        stmt = select(
            stock_analysis_results.c.ticker,
            stock_analysis_results.c.intrinsic_value_estimate,
            stock_analysis_results.c.current_price,
            stock_analysis_results.c.margin_of_safety,
            stock_analysis_results.c.ai_reasoning,
            stock_analysis_results.c.conviction_score,
        ).where(stock_analysis_results.c.conviction_score.isnot(None))

        results = conn.execute(stmt).mappings().all()

        if not results:
            print("No stocks with sufficient data to rank.")
            return

        ranking_data = []
        for row in results:
            try:
                intrinsic_value = float(row["intrinsic_value_estimate"] or 0.0)
                current_price = row.get("current_price")
                if current_price is None or current_price == 0:
                    try:
                        current_price_str = row.get("ai_reasoning", "").split("$")[-1]
                        current_price = float(
                            current_price_str.replace(",", "").strip()
                        )
                    except Exception:
                        current_price = None
                margin_of_safety = row.get("margin_of_safety")
                if margin_of_safety is not None:
                    margin_of_safety = float(margin_of_safety)
                elif intrinsic_value > 0 and current_price:
                    margin_of_safety = 1 - (current_price / intrinsic_value)
                else:
                    margin_of_safety = None

                conviction_val = row["conviction_score"]
                if (
                    margin_of_safety is not None
                    and intrinsic_value > 0
                    and current_price
                    and conviction_val is not None
                ):
                    ranking_score = (margin_of_safety * 100.0) + float(conviction_val)

                    ranking_data.append(
                        {
                            "ticker": row["ticker"],
                            "ranking_score": ranking_score,
                            "margin_of_safety": f"{margin_of_safety:.2%}",
                            "conviction": conviction_val,
                        }
                    )
            except (ValueError, IndexError):
                continue  # Skip if price parsing fails

        # Sort from best to worst
        ranked_list = sorted(
            ranking_data, key=lambda x: x["ranking_score"], reverse=True
        )

        print("\n--- 📊 Top 10 Ranked Investment Opportunities ---")
        for i, stock in enumerate(ranked_list[:10]):
            print(
                f"#{i+1}: {stock['ticker']} "
                f"(Rank Score: {stock['ranking_score']:.2f}, "
                f"MoS: {stock['margin_of_safety']}, "
                f"Conviction: {stock['conviction']})"
            )


def _save_resume_state(ticker: str):
    """Saves the last successfully processed ticker to a state file."""
    try:
        state_dir = ".cache"
        if not os.path.exists(state_dir):
            os.makedirs(state_dir)
        state_file = os.path.join(state_dir, "resume_state.json")
        # Atomic write (sort of)
        temp_file = state_file + ".tmp"
        with open(temp_file, "w") as f:
            json.dump({"last_processed_ticker": ticker, "updated_at": datetime.now(timezone.utc).isoformat()}, f)
        os.replace(temp_file, state_file)
    except Exception as e:
        print(f"Warning: Failed to save resume state: {e}")


def _process_job_batch(
    jobs: List[Dict[str, Any]],
    max_workers: int,
    trigger_eval: TriggerEvaluator,
) -> Tuple[List[Dict[str, Any]], List[Tuple[Dict[str, Any], Dict[str, Any]]], bool]:
    """
    รันชุดงาน (batch) หนึ่งครั้งแล้วคืนทั้ง success, failure และ flag ว่า weekly run ถูกใช้ไปหรือยัง
    """
    if not jobs:
        return [], [], False

    worker_count = max(1, min(int(max_workers), len(jobs)))
    successes: List[Dict[str, Any]] = []
    failures: List[Tuple[Dict[str, Any], Dict[str, Any]]] = []
    weekly_consumed = False

    with ProcessPoolExecutor(max_workers=worker_count) as executor:
        futures = {executor.submit(_execute_ticker_job, job): job for job in jobs}
        for future in as_completed(futures):
            job = futures[future]
            ticker = job["ticker"]
            try:
                result = future.result()
            except Exception as exc:
                print(
                    f"!!! FAILED UNIFIED ANALYSIS FOR {ticker} due to worker exception: {exc} !!!"
                )
                failures.append(
                    (
                        job,
                        {
                            "ticker": ticker,
                            "status": "exception",
                            "error": str(exc),
                        },
                    )
                )
                continue

            status = result.get("status")
            if status in TERMINAL_SUCCESS_STATUSES:
                successes.append(result)
                if result.get("weekly_trigger"):
                    weekly_consumed = True

                latest_filing_date = result.get("latest_filing_date")
                if latest_filing_date:
                    try:
                        if isinstance(latest_filing_date, str):
                            mark_date = datetime.fromisoformat(
                                latest_filing_date
                            ).date()
                        else:
                            mark_date = latest_filing_date
                        trigger_eval.mark_filing_processed(ticker, mark_date)
                    except Exception:
                        pass
                
                # --- Intelligent Bookmark: Save State ---
                _save_resume_state(ticker)
            else:
                failures.append((job, result))
                error = result.get("error")
                if error:
                    print(f"[Worker:{ticker}] {error}")

    return successes, failures, weekly_consumed


def run_unified_analysis(
    tickers_list,
    *,
    max_workers: int = 12,
    max_retries: Optional[int] = None,
    retry_delay_seconds: Optional[int] = None,
):
    print(f"--- STARTING UNIFIED ANALYSIS FOR {len(tickers_list)} TICKERS ---")
    db_engine = DatabaseConnector().get_engine()
    trigger_eval = TriggerEvaluator(db_engine)
    weekly_due = trigger_eval.is_weekly_price_due()

    env_retry_default = _get_env_int("UNIFIED_MAX_RETRIES", 1)
    env_delay_default = _get_env_int("UNIFIED_RETRY_DELAY_SECONDS", 30)

    try:
        max_workers = int(max_workers)
    except (TypeError, ValueError):
        max_workers = 1
    max_workers = max(1, max_workers)

    if max_retries is None:
        max_retries = env_retry_default
    else:
        try:
            max_retries = int(max_retries)
        except (TypeError, ValueError):
            max_retries = env_retry_default
    max_retries = max(0, max_retries)

    if retry_delay_seconds is None:
        retry_delay_seconds = env_delay_default
    else:
        try:
            retry_delay_seconds = int(retry_delay_seconds)
        except (TypeError, ValueError):
            retry_delay_seconds = env_delay_default
    retry_delay_seconds = max(0, retry_delay_seconds)

    jobs: List[Dict[str, Any]] = []
    for ticker in tickers_list:
        job = _evaluate_ticker_for_run(ticker, db_engine, trigger_eval, weekly_due)
        if not job:
            continue
        print(f"--- TRIGGERS for {ticker}: {', '.join(job['run_reasons'])} ---")
        jobs.append(job)

    if not jobs:
        print("No tickers scheduled for processing. Nothing to do.")
        return

    initial_worker_count = max(1, min(max_workers, len(jobs)))
    print(
        f"Dispatching {len(jobs)} tickers across up to {initial_worker_count} worker(s)..."
    )

    processed_order: List[str] = []
    processed_seen: set[str] = set()
    weekly_run_consumed = False

    jobs_to_run = list(jobs)
    retries_left = max_retries
    attempt = 0
    final_failures: List[Tuple[Dict[str, Any], Dict[str, Any]]] = []

    while jobs_to_run:
        attempt += 1
        if attempt > 1:
            print(
                f"--- RETRY ROUND {attempt - 1}/{max_retries} : Reprocessing {len(jobs_to_run)} ticker(s) ---"
            )

        successes, failures, weekly_flag = _process_job_batch(
            jobs_to_run, max_workers, trigger_eval
        )
        if weekly_flag:
            weekly_run_consumed = True

        for res in successes:
            ticker = res.get("ticker")
            if ticker and ticker not in processed_seen:
                processed_seen.add(ticker)
                processed_order.append(ticker)

        if not failures:
            final_failures = []
            break

        final_failures = failures
        if retries_left == 0:
            break

        retries_left -= 1
        failed_names = ", ".join(job["ticker"] for job, _ in failures)
        print(
            f"Retrying {len(failures)} ticker(s) after {retry_delay_seconds} seconds: {failed_names}"
        )
        if retry_delay_seconds > 0:
            time.sleep(retry_delay_seconds)

        new_jobs: List[Dict[str, Any]] = []
        for job, _ in failures:
            retry_job = dict(job)
            retry_job["retry_count"] = job.get("retry_count", 0) + 1
            new_jobs.append(retry_job)
        jobs_to_run = new_jobs

    if final_failures:
        failed_names = ", ".join(job["ticker"] for job, _ in final_failures)
        print(
            f"Tickers still failing after {attempt} attempt(s): {failed_names}. Inspect logs for details."
        )

    if weekly_due and weekly_run_consumed:
        trigger_eval.mark_weekly_price_run()

    if processed_order:
        print(
            f"Processed {len(processed_order)} tickers. For post-process, run: python -m backend.post_process_runner"
        )
        run_ranking_system(db_engine)
    else:
        print("No tickers finished successfully; skipping ranking.")


if __name__ == "__main__":
    multiprocessing.freeze_support()

    try:
        sec_client = SecClient()
        sec_ticker_map = sec_client.get_all_company_tickers()
    except Exception as exc:
        print(f"Failed to fetch tickers from SEC API: {exc}")
    else:
        if not sec_ticker_map:
            print("SEC API did not return tickers; aborting unified analysis.")
        else:
            tickers_to_analyze = sorted(
                {
                    (info or {}).get("ticker", "").upper()
                    for info in sec_ticker_map.values()
                    if (info or {}).get("ticker")
                }
            )

            if not tickers_to_analyze:
                print("SEC API returned no valid tickers; aborting unified analysis.")
            else:
                # --- NEW: TEST_TICKER & Intelligent Resume Logic ---
                from backend.src.config import get_env_str
                test_ticker = get_env_str("TEST_TICKER")
                resume_file = os.path.join(".cache", "resume_state.json")

                if test_ticker:
                    targets = [t.strip().upper() for t in test_ticker.split(",") if t.strip()]
                    print(f"\n!!! TEST MODE ACTIVATED: Only processing {', '.join(targets)} !!!\n")
                    # Filter specifically for the test tickers, or just use them directly
                    tickers_to_analyze = targets
                else:
                    # Resume Logic
                    if os.path.exists(resume_file):
                        try:
                            with open(resume_file, "r") as f:
                                state = json.load(f)
                                last_ticker = state.get("last_processed_ticker")
                                if last_ticker and last_ticker in tickers_to_analyze:
                                    idx = tickers_to_analyze.index(last_ticker)
                                    print(f"\n>>> Intelligent Bookmark Found: Resuming from after '{last_ticker}' (skipping {idx+1} completed tickers). <<<\n")
                                    tickers_to_analyze = tickers_to_analyze[idx+1:]
                        except Exception as e:
                            print(f"Warning: Could not load resume state: {e}")

                batch_size = 12
                max_workers = 6
                total_batches = (len(tickers_to_analyze) + batch_size - 1) // batch_size

                for batch_index in range(total_batches):
                    start = batch_index * batch_size
                    end = start + batch_size
                    batch = tickers_to_analyze[start:end]
                    if not batch:
                        continue

                    print(
                        f"=== Processing SEC batch {batch_index + 1}/{total_batches}: "
                        f"{', '.join(batch)} ==="
                    )

                    try:
                        run_unified_analysis(batch, max_workers=min(max_workers, len(batch)))
                    except Exception as exc:
                        print(
                            f"Batch {batch_index + 1} failed with unexpected error: {exc}"
                        )
