"""
backend/src/jobs/weekly_refresh_job.py

Lightweight weekly refresh runner for a single ticker.
- Fetches latest price and market cap (Finnhub primary, yfinance fallback)
- Updates stock_analysis_results.ai_reasoning + analysis_date (if row exists)
- Updates stocks.market_cap (if market cap available)
- Staleness watcher: forces refresh if last_analysis_date older than staleness_days
- Writes per-ticker system_status keys for visibility and debugging:
    - weekly:{ticker} (status: price_refreshed | skipped_recent_price | skipped_no_price)
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any

from backend.src.database.db_connector import DatabaseConnector
from backend.src.jobs.db_ops import set_system_status
from backend.src.api_clients.yfinance_client import YFinanceClient
from backend.src.database.models import stock_analysis_results, stocks
from sqlalchemy import select, update

# Finnhub client is optional; we prefer it for price and profile
try:
    from backend.src.api_clients.finnhub_client import FinnhubClient
except Exception:
    FinnhubClient = None  # type: ignore


def _iso(dt) -> Optional[str]:
    if dt is None:
        return None
    try:
        return dt.isoformat()
    except Exception:
        try:
            return str(dt)
        except Exception:
            return None


def perform_weekly_price_refresh(
    db_engine,
    ticker: str,
    *,
    min_age_hours: int = 24,
    staleness_days: int = 7,
    force: bool = False,
) -> Optional[Dict[str, Any]]:
    """
    Perform a lightweight price + market-cap refresh for a ticker.

    Returns a dict with keys: ticker, status, price (if available), market_cap (if available).
    Returns None or {} to indicate caller should proceed with full analysis fallback.
    """
    ticker = ticker.upper()
    now = datetime.now(timezone.utc)

    # 1) Determine last "price" update time: use latest stock_analysis_results.analysis_date
    last_analysis_dt = None
    with db_engine.connect() as conn:
        last_analysis_dt = conn.execute(
            select(stock_analysis_results.c.analysis_date)
            .where(stock_analysis_results.c.ticker == ticker)
            .order_by(stock_analysis_results.c.analysis_date.desc())
            .limit(1)
        ).scalar_one_or_none()

    # If last_analysis_dt is a date-like string, try to parse; we treat None as never
    age = None
    if last_analysis_dt:
        try:
            age = (
                now - last_analysis_dt
                if isinstance(last_analysis_dt, datetime)
                else now - datetime.fromisoformat(str(last_analysis_dt))
            )
        except Exception:
            try:
                # best-effort: cast to datetime
                age = now - datetime.fromisoformat(str(last_analysis_dt))
            except Exception:
                age = None

    staleness_force = False
    if age is not None:
        if age > timedelta(days=staleness_days):
            staleness_force = True

    # Skip decision: if not forced by staleness and not explicit force flag
    if not force and not staleness_force:
        if age is not None and age < timedelta(hours=min_age_hours):
            # recent enough -> skip
            reason = f"price updated {int(age.total_seconds()/3600)}h ago (<{min_age_hours}h threshold)"
            print(f"Skipping {ticker}: {reason}")
            try:
                set_system_status(
                    db_engine,
                    f"weekly:{ticker}",
                    {
                        "phase": "weekly",
                        "ticker": ticker,
                        "status": "skipped_recent_price",
                        "reason": reason,
                        "last_analysis_date": _iso(last_analysis_dt),
                        "checked_at": now.isoformat(),
                    },
                )
            except Exception:
                pass
            # return a compact result indicating skip (so unified_runner can count weekly_run_consumed)
            return {
                "ticker": ticker,
                "status": "skipped_recent_price",
                "reason": reason,
            }
    # else: either force True or staleness_force True -> proceed to fetch

    # 2) Fetch price and market cap
    price = None
    market_cap = None
    price_source = None

    # Try Finnhub first for price and market cap
    if FinnhubClient is not None:
        try:
            fh = FinnhubClient()
            price = fh.get_latest_price(ticker)
            if price is not None:
                price_source = "finnhub"
            profile = fh.get_company_profile(ticker) or {}
            mc = profile.get("marketCapitalization")
            if mc is not None:
                try:
                    mc_float = float(mc)
                    # Finnhub marketCapitalization is reported in millions of USD
                    market_cap = int(mc_float * 1_000_000)
                except Exception:
                    market_cap = None
        except Exception:
            price = None
            market_cap = None

    # Fallback to yfinance
    if price is None or market_cap is None:
        try:
            yf = YFinanceClient()
            # price
            if price is None:
                if hasattr(yf, "get_current_price"):
                    price = yf.get_current_price(ticker)
                elif hasattr(yf, "get_price"):
                    price = yf.get_price(ticker)
            # market cap
            if market_cap is None:
                info = yf.get_company_info(ticker) or {}
                mc = info.get("marketCap") or info.get("market_cap") or None
                if mc is not None:
                    try:
                        market_cap = int(mc)
                    except Exception:
                        try:
                            market_cap = int(float(mc))
                        except Exception:
                            market_cap = None
            if price_source is None:
                price_source = "yfinance"
        except Exception:
            # both sources failed partially
            pass

    # 3) If price is None -> log skip reason and return a small result so caller can decide to full-run
    if price is None and not staleness_force and not force:
        reason = "API returned no price"
        print(f"Skipping {ticker}: {reason}")
        try:
            set_system_status(
                db_engine,
                f"weekly:{ticker}",
                {
                    "phase": "weekly",
                    "ticker": ticker,
                    "status": "skipped_no_price",
                    "reason": reason,
                    "checked_at": now.isoformat(),
                },
            )
        except Exception:
            pass
        return {"ticker": ticker, "status": "skipped_no_price", "reason": reason}

    # 4) Persist results: update stock_analysis_results (if row exists) and stocks.market_cap (if available)
    updated = False
    with db_engine.connect() as conn:
        existing = conn.execute(
            select(stock_analysis_results.c.ticker).where(
                stock_analysis_results.c.ticker == ticker
            )
        ).first()
        if existing:
            try:
                stmt = (
                    update(stock_analysis_results)
                    .where(stock_analysis_results.c.ticker == ticker)
                    .values(
                        ai_reasoning=f"Price-only refresh: current_price=${price} (src={price_source})",
                        analysis_date=now,
                    )
                )
                conn.execute(stmt)
                updated = True
            except Exception as e:
                print(
                    f"[PRICE-ONLY] Failed to update stock_analysis_results for {ticker}: {e}"
                )
        else:
            # prefer not to create new analysis rows in price-only
            print(
                f"[PRICE-ONLY] No existing analysis row for {ticker}; not inserting a new full_analysis row."
            )

        # Update stocks.market_cap if available
        if market_cap is not None:
            try:
                stmt2 = (
                    update(stocks)
                    .where(stocks.c.ticker == ticker)
                    .values(market_cap=int(market_cap), last_updated=now)
                )
                res = conn.execute(stmt2)
                # if no row existed, this won't insert; that's fine (we avoid creating stub)
                print(
                    f"[PRICE-ONLY] Updated stocks.market_cap for {ticker} -> {market_cap}"
                )
            except Exception as e:
                print(
                    f"[PRICE-ONLY] Failed to update stocks.market_cap for {ticker}: {e}"
                )

        conn.commit()

    # 5) Persist concise system status for auditable history
    try:
        set_system_status(
            db_engine,
            f"weekly:{ticker}",
            {
                "phase": "weekly",
                "ticker": ticker,
                "status": "price_refreshed",
                "price": float(price) if price is not None else None,
                "price_source": price_source,
                "market_cap": int(market_cap) if market_cap is not None else None,
                "last_analysis_date": _iso(last_analysis_dt),
                "refreshed_at": now.isoformat(),
                "staleness_force": bool(staleness_force),
            },
        )
    except Exception:
        pass

    return {
        "ticker": ticker,
        "status": "price_refreshed",
        "price": float(price) if price is not None else None,
        "market_cap": int(market_cap) if market_cap is not None else None,
        "weekly_trigger": True,
    }


if __name__ == "__main__":  # CLI convenience to run standalone
    db_engine = DatabaseConnector().get_engine()
    args = sys.argv[1:] or []
    if not args:
        print(
            "Usage: python -m backend.src.jobs.weekly_refresh_job TICKER1 [TICKER2 ...]"
        )
        sys.exit(1)
    for t in args:
        print("--- Running weekly refresh for:", t)
        res = perform_weekly_price_refresh(db_engine, t)
        print(res)
