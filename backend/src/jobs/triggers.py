from __future__ import annotations

from datetime import datetime, timedelta, timezone, date
from typing import Optional, Tuple

from sqlalchemy import select

from backend.src.database.models import (
    sec_filings_metadata,
    stock_analysis_results,
)
from backend.src.jobs.db_ops import get_system_status, set_system_status

FORMS_OF_INTEREST = {"10-K", "N-CSR", "N-CSRS"}


class TriggerEvaluator:
    """Decides when to run deep analysis based on filings and weekly cadence."""

    def __init__(
        self,
        db_engine,
        *,
        filing_forms: set[str] | None = None,
        weekly_interval_days: int = 7,
    ) -> None:
        self.db_engine = db_engine
        self.filing_forms = filing_forms or FORMS_OF_INTEREST
        self.weekly_interval = timedelta(days=max(1, weekly_interval_days))

    # ----- Filing helpers -----
    def latest_sec_filing(self, ticker: str) -> Tuple[Optional[date], Optional[str]]:
        with self.db_engine.connect() as conn:
            row = (
                conn.execute(
                    select(
                        sec_filings_metadata.c.filing_date,
                        sec_filings_metadata.c.form_type,
                    )
                    .where(
                        sec_filings_metadata.c.ticker == ticker,
                        sec_filings_metadata.c.form_type.in_(self.filing_forms),
                    )
                    .order_by(sec_filings_metadata.c.filing_date.desc())
                    .limit(1)
                ).first()
            )
        if not row:
            return None, None
        filing_date, form_type = row
        return filing_date, form_type

    def last_processed_filing(self, ticker: str) -> Optional[date]:
        status = get_system_status(self.db_engine, f"status:{ticker}")
        if not status:
            return None
        value = status.get("latest_filing_date")
        if not value:
            return None
        try:
            return datetime.fromisoformat(str(value)).date()
        except Exception:
            return None

    def mark_filing_processed(self, ticker: str, filing_date: date) -> None:
        current = get_system_status(self.db_engine, f"status:{ticker}") or {}
        payload = {**current}
        payload.setdefault("status", "completed")
        payload["phase"] = "standard"
        payload["ticker"] = ticker
        payload["latest_filing_date"] = filing_date.isoformat()
        updated_at = datetime.now(timezone.utc).isoformat()
        payload["latest_filing_processed_at"] = updated_at
        payload["updated_at"] = updated_at
        set_system_status(
            self.db_engine,
            f"status:{ticker}",
            payload,
        )

    def has_new_filing(self, ticker: str) -> Tuple[bool, Optional[date]]:
        latest_date, _ = self.latest_sec_filing(ticker)
        if not latest_date:
            return False, None
        last_processed = self.last_processed_filing(ticker)
        if last_processed is None or latest_date > last_processed:
            return True, latest_date
        return False, latest_date

    # ----- Weekly cadence helpers -----

    def is_weekly_price_due(self, now: Optional[datetime] = None) -> bool:
        now = now or datetime.now(timezone.utc)
        if now.weekday() not in (5, 6):
            return False

        status = get_system_status(self.db_engine, "weekly:last_run")
        if not status:
            return True

        iso_year = status.get("iso_year")
        iso_week = status.get("iso_week")
        if iso_year is None or iso_week is None:
            return True

        current_year, current_week, _ = now.isocalendar()
        try:
            iso_year = int(iso_year)
            iso_week = int(iso_week)
        except Exception:
            return True

        return (iso_year, iso_week) != (current_year, current_week)

    def mark_weekly_price_run(self, run_time: Optional[datetime] = None) -> None:
        run_time = run_time or datetime.now(timezone.utc)
        iso_year, iso_week, _ = run_time.isocalendar()
        set_system_status(
            self.db_engine,
            "weekly:last_run",
            {
                "phase": "weekly",
                "scope": "global",
                "last_run_at": run_time.isoformat(),
                "iso_year": int(iso_year),
                "iso_week": int(iso_week),
            },
        )

    def last_analysis_timestamp(self, ticker: str) -> Optional[datetime]:
        with self.db_engine.connect() as conn:
            ts = (
                conn.execute(
                    select(stock_analysis_results.c.analysis_date)
                    .where(stock_analysis_results.c.ticker == ticker)
                    .order_by(stock_analysis_results.c.analysis_date.desc())
                    .limit(1)
                ).scalar_one_or_none()
            )
        return ts
