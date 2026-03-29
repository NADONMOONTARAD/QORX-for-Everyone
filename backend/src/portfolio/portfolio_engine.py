"""Computation engine for the unified Portfolio snapshot.

This module ingests the latest analysis outputs plus transaction history and
rolls forward the portfolio_state / portfolio_positions tables according to
the AI Buffett ladder spec.
"""

from __future__ import annotations

import math
from datetime import date, datetime, timezone
from typing import Any, Iterable, Optional

from sqlalchemy import Select, asc, delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from backend.src.api_clients.yfinance_client import YFinanceClient
# from backend.src.api_clients.fred_client import FredClient  # Temporarily disabled (FRED API unavailable)
from backend.src.database.models import (
    portfolio_checkpoints,
    portfolio_positions,
    portfolio_state,
    stock_analysis_results,
    transactions,
)
from backend.src.portfolio.rules import (
    PortfolioDirective,
    compute_portfolio_directive,
    conviction_floor,
    determine_reallocation_level,
)
from backend.src.jobs.db_ops import get_system_status, set_system_status


def _to_float(value: Any) -> float:
    if value is None:
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _ensure_datetime(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day, tzinfo=timezone.utc)
    try:
        return datetime.fromisoformat(str(value))
    except Exception:
        return None


def _ensure_date(value: Any) -> Optional[date]:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    dt = _ensure_datetime(value)
    if dt:
        return dt.date()
    return None


def _clamp(value: float, lower: float = 0.0, upper: float = 100.0) -> float:
    return max(lower, min(upper, value))


_RISK_FREE_CACHE_KEY = "metrics:risk_free_rate"


def _resolve_risk_free_rate(
    db_engine,
    *,
    fallback_rate: Optional[float] = None,
    max_age_days: int = 7,
) -> float:
    """
    คืนค่า risk-free rate (%) โดยดูจากระบบ cache ใน system_status
    ถ้าเก่ากว่า max_age_days จะดึงจาก FRED ใหม่
    """
    fallback = float(fallback_rate) if fallback_rate is not None else 2.16
    now = datetime.now(timezone.utc)

    cached_value = get_system_status(db_engine, _RISK_FREE_CACHE_KEY) or {}
    cached_rate = cached_value.get("rate")
    cached_ts = cached_value.get("fetched_at")
    cached_dt = _ensure_datetime(cached_ts)

    if (
        cached_rate is not None
        and cached_dt is not None
        and (now - cached_dt).days <= max_age_days
    ):
        try:
            return float(cached_rate)
        except (TypeError, ValueError):
            pass

    # fred_client = FredClient()
    # latest_rate = fred_client.get_risk_free_rate()
    latest_rate = None
    if latest_rate is not None:
        rate_value = float(latest_rate)
        set_system_status(
            db_engine,
            _RISK_FREE_CACHE_KEY,
            {"rate": rate_value, "fetched_at": now.isoformat()},
        )
        return rate_value

    if cached_rate is not None:
        try:
            return float(cached_rate)
        except (TypeError, ValueError):
            pass

    return fallback


def _enforce_checkpoint_retention(conn, today: date, years: int = 10):
    """ลบ checkpoint ที่เกินช่วง years ปี (คำนวณแบบเดือนต่อเดือน)."""
    cutoff_index = (today.year * 12 + today.month) - (years * 12)
    if cutoff_index <= 0:
        return
    expr = (portfolio_checkpoints.c.year * 12) + portfolio_checkpoints.c.month
    conn.execute(
        delete(portfolio_checkpoints).where(expr < cutoff_index)
    )


def _load_analysis_rows(conn) -> dict[str, dict]:
    stmt: Select = select(
        stock_analysis_results.c.ticker,
        stock_analysis_results.c.analysis_date,
        stock_analysis_results.c.conviction_score,
        stock_analysis_results.c.margin_of_safety,
        stock_analysis_results.c.current_price,
        stock_analysis_results.c.portfolio_directive,
    )
    rows = conn.execute(stmt).mappings().all()
    data: dict[str, dict] = {}
    for row in rows:
        ticker = (row["ticker"] or "").upper()
        if not ticker:
            continue
        data[ticker] = dict(row)
    return data


def _load_transactions(conn) -> list[dict]:
    stmt: Select = (
        select(transactions)
        .order_by(asc(transactions.c.date), asc(transactions.c.id))
        .execution_options(stream_results=False)
    )
    return [dict(row) for row in conn.execute(stmt).mappings().all()]


def _aggregate_transactions(tx_rows: Iterable[dict]) -> tuple[dict[str, dict], float]:
    positions: dict[str, dict] = {}
    cash_balance = 0.0
    for row in tx_rows:
        tx_type = (row.get("type") or "").upper()
        ticker = (row.get("ticker") or "").upper()
        amount = _to_float(row.get("amount"))
        price = _to_float(row.get("price"))
        quantity = _to_float(row.get("quantity"))

        if tx_type == "ADD_CASH":
            cash_balance += amount
            continue
        if tx_type == "WITHDRAW":
            cash_balance -= amount
            continue
        if tx_type not in {"BUY", "SELL"}:
            continue

        if amount == 0.0 and price != 0.0:
            amount = price * quantity

        pos = positions.setdefault(
            ticker, {"quantity": 0.0, "cost_basis": 0.0, "realized_pnl": 0.0}
        )

        if tx_type == "BUY":
            pos["quantity"] += quantity
            pos["cost_basis"] += amount
            cash_balance -= amount
        elif tx_type == "SELL":
            qty_available = pos["quantity"]
            qty_to_sell = quantity
            if qty_available <= 0:
                cash_balance += amount
                continue
            if qty_to_sell > qty_available:
                qty_to_sell = qty_available
            avg_cost = pos["cost_basis"] / qty_available if qty_available else 0.0
            cost_reduction = avg_cost * qty_to_sell
            pos["quantity"] -= qty_to_sell
            pos["cost_basis"] = max(0.0, pos["cost_basis"] - cost_reduction)
            pos["realized_pnl"] += amount - cost_reduction
            cash_balance += amount
    return positions, cash_balance


def _load_existing_positions(conn) -> dict[str, dict]:
    rows = conn.execute(select(portfolio_positions)).mappings().all()
    return {row["ticker"]: dict(row) for row in rows}


def _load_state(conn) -> Optional[dict]:
    row = (
        conn.execute(
            select(portfolio_state).where(portfolio_state.c.state_id == 1)
        )
        .mappings()
        .first()
    )
    return dict(row) if row else None


def refresh_portfolio_snapshot(
    db_engine,
    *,
    risk_free_rate: Optional[float] = None,
    snapshot_date: Optional[date] = None,
) -> dict:
    """Recompute portfolio_state/checkpoints/positions from latest data."""

    today = snapshot_date or datetime.now(timezone.utc).date()
    price_client = None

    with db_engine.begin() as conn:
        analysis_map = _load_analysis_rows(conn)
        tx_rows = _load_transactions(conn)
        existing_positions = _load_existing_positions(conn)
        state_row = _load_state(conn)

        holdings, cash_balance = _aggregate_transactions(tx_rows)

        # Acquire prices for tickers (prefer analysis snapshot, fallback to YF)
        tickers = set(analysis_map.keys()) | set(holdings.keys())
        price_cache: dict[str, float] = {}
        entries: dict[str, dict] = {}

        for ticker in sorted(tickers):
            analysis = analysis_map.get(ticker, {})
            position = holdings.get(ticker, {"quantity": 0.0, "cost_basis": 0.0})
            directive_raw = analysis.get("portfolio_directive")

            conviction_score = analysis.get("conviction_score")
            margin_of_safety = analysis.get("margin_of_safety")
            analysis_date = _ensure_datetime(analysis.get("analysis_date"))

            if directive_raw and isinstance(directive_raw, dict):
                directive_dict = dict(directive_raw)
            else:
                directive_dict = compute_portfolio_directive(
                    conviction_score, margin_of_safety
                ).to_dict()

            price = _to_float(analysis.get("current_price"))
            if price == 0.0:
                if price_client is None:
                    price_client = YFinanceClient()
                try:
                    fetched_price = price_client.get_current_price(ticker)
                    price = float(fetched_price) if fetched_price else 0.0
                except Exception:
                    price = 0.0
            price_cache[ticker] = price

            quantity = position.get("quantity", 0.0)
            cost_basis = position.get("cost_basis", 0.0)
            current_value = price * quantity

            entry = {
                "ticker": ticker,
                "analysis_date": analysis_date,
                "conviction_score": float(conviction_score)
                if conviction_score is not None
                else None,
                "margin_of_safety": float(margin_of_safety)
                if margin_of_safety is not None
                else None,
                "directive": directive_dict,
                "current_price": price,
                "quantity": quantity,
                "cost_basis": cost_basis,
                "current_value": current_value,
                "target_pct_base": float(directive_dict.get("target_pct", 0.0) or 0.0),
                "notes": directive_dict.get("notes"),
                "action_label_base": directive_dict.get("label"),
                "reallocation_flag": False,
                "adjustments": {},
            }
            entries[ticker] = entry

        portfolio_value = cash_balance + sum(e["current_value"] for e in entries.values())

        # Avoid zero division for empty portfolios
        if portfolio_value <= 0:
            portfolio_value = 0.0
        # Compute portfolio weights
        for entry in entries.values():
            current_value = entry["current_value"]
            current_pct = (
                (current_value / portfolio_value * 100.0) if portfolio_value > 0 else 0.0
            )
            entry["current_pct"] = round(current_pct, 4)
            entry["target_pct_final"] = _clamp(entry["target_pct_base"])
            entry["margin_of_safety_pct"] = (
                float(entry["margin_of_safety"] or 0.0) * 100.0
            )

        # Reallocation logic (pairwise)
        candidates = [
            entry
            for entry in entries.values()
            if (entry.get("conviction_score") or 0.0) >= 80.0
            and entry["margin_of_safety_pct"] >= 20.0
        ]

        for entry in entries.values():
            current_pct = entry.get("current_pct", 0.0)
            if current_pct <= 0:
                continue
            best_choice = None
            for candidate in candidates:
                if candidate["ticker"] == entry["ticker"]:
                    continue
                delta_conv = (candidate.get("conviction_score") or 0.0) - (
                    entry.get("conviction_score") or 0.0
                )
                delta_mos = candidate["margin_of_safety_pct"] - entry["margin_of_safety_pct"]
                level = determine_reallocation_level(delta_conv, delta_mos)
                if not level:
                    continue
                level_label, trim_pct = level
                floor = conviction_floor(entry.get("conviction_score"))
                max_trim = max(0.0, current_pct - floor)
                effective_trim = min(trim_pct, max_trim)
                if effective_trim <= 0:
                    continue
                if not best_choice or effective_trim > best_choice["trim"]:
                    best_choice = {
                        "candidate": candidate,
                        "trim": effective_trim,
                        "label": level_label,
                        "floor": floor,
                    }
            if best_choice:
                entry["reallocation_flag"] = True
                entry["adjustments"]["reallocate_level"] = best_choice["label"]
                entry["adjustments"]["trim_pct"] = best_choice["trim"]
                candidate = best_choice["candidate"]
                candidate.setdefault("adjustments", {}).setdefault(
                    "reallocate_from", []
                ).append(
                    {
                        "ticker": entry["ticker"],
                        "delta_pct": best_choice["trim"],
                        "level": best_choice["label"],
                    }
                )
                entry["target_pct_final"] = _clamp(
                    max(
                        best_choice["floor"],
                        min(entry["target_pct_final"], current_pct - best_choice["trim"]),
                    )
                )
                candidate["target_pct_final"] = _clamp(
                    candidate["target_pct_final"] + best_choice["trim"]
                )
                candidate["reallocation_flag"] = True

        # Compute delta & action summaries
        for entry in entries.values():
            target_final = _clamp(entry.get("target_pct_final", 0.0))
            current_pct = entry.get("current_pct", 0.0)
            delta_pct = round(target_final - current_pct, 4)
            entry["delta_pct"] = delta_pct
            if delta_pct > 0.5:
                action_label = "BUY"
                action_text = f"Buy +{delta_pct:.1f}% → Target {target_final:.1f}%"
            elif delta_pct < -0.5:
                label_prefix = "Trim"
                if entry.get("reallocation_flag"):
                    label_prefix = "Reallocate"
                action_label = "TRIM"
                action_text = f"{label_prefix} {abs(delta_pct):.1f}% → Target {target_final:.1f}%"
            else:
                action_label = "HOLD"
                action_text = f"Hold @ {current_pct:.1f}%"
            entry["action_label"] = action_label
            base_label = entry.get("action_label_base")
            if base_label:
                action_text = f"{action_text} | {base_label}"
            entry["action"] = action_text

            cost_basis = entry.get("cost_basis", 0.0)
            current_value = entry.get("current_value", 0.0)
            if cost_basis > 0:
                entry["total_return"] = round(
                    ((current_value - cost_basis) / cost_basis) * 100.0, 4
                )
            else:
                entry["total_return"] = None

        # Add cash pseudo-entry
        entries["CASH"] = {
            "ticker": "CASH",
            "analysis_date": None,
            "conviction_score": None,
            "margin_of_safety": None,
            "margin_of_safety_pct": None,
            "directive": PortfolioDirective(
                mode="hold",
                target_pct=0.0,
                label="ถือเงินสดรอโอกาส",
                ladder_stage="cash",
                notes="Cash buffer",
                metadata={},
            ).to_dict(),
            "current_price": 1.0,
            "quantity": cash_balance,
            "cost_basis": cash_balance,
            "current_value": cash_balance,
            "current_pct": (cash_balance / portfolio_value * 100.0)
            if portfolio_value > 0
            else 0.0,
            "target_pct_base": None,
            "target_pct_final": None,
            "delta_pct": None,
            "action_label": "HOLD",
            "action": "Hold cash",
            "total_return": None,
            "reallocation_flag": False,
            "adjustments": {},
            "notes": "Cash position",
        }

        # Prepare portfolio_state update
        prev_value = _to_float(state_row.get("portfolio_value")) if state_row else 0.0
        start_value = _to_float(state_row.get("start_value")) if state_row else 0.0
        start_date = _ensure_date(state_row.get("start_date")) if state_row else None
        total_days = int(state_row.get("total_days") or 0) if state_row else 0
        sum_return = _to_float(state_row.get("sum_return")) if state_row else 0.0
        sum_squared = _to_float(state_row.get("sum_squared_diff")) if state_row else 0.0
        portfolio_peak = _to_float(state_row.get("portfolio_peak")) if state_row else 0.0
        max_drawdown = _to_float(state_row.get("max_drawdown")) if state_row else 0.0
        last_update = _ensure_date(state_row.get("last_update")) if state_row else None

        if start_value <= 0 and portfolio_value > 0:
            start_value = portfolio_value
            start_date = today

        rf_existing = (
            float(state_row.get("risk_free_rate"))
            if state_row and state_row.get("risk_free_rate") is not None
            else None
        )
        if risk_free_rate is not None:
            rf_percent = float(risk_free_rate)
        else:
            rf_percent = _resolve_risk_free_rate(
                db_engine, fallback_rate=rf_existing
            )
        rf_decimal = rf_percent / 100.0

        if portfolio_value > portfolio_peak:
            portfolio_peak = portfolio_value
        drawdown_pct = (
            ((portfolio_value - portfolio_peak) / portfolio_peak) * 100.0
            if portfolio_peak > 0
            else 0.0
        )
        if drawdown_pct < max_drawdown:
            max_drawdown = drawdown_pct

        daily_return = (
            (portfolio_value - prev_value) / prev_value if prev_value > 0 else 0.0
        )
        if last_update != today and prev_value > 0:
            total_days += 1
            sum_return += daily_return
            sum_squared += daily_return**2

        avg_daily_return = (sum_return / total_days) if total_days > 0 else 0.0
        variance = (
            (sum_squared / total_days) - (avg_daily_return**2)
            if total_days > 0
            else 0.0
        )
        variance = max(variance, 0.0)
        daily_std = math.sqrt(variance)
        sharpe_ratio = None
        if total_days > 0 and daily_std > 0:
            daily_rf = rf_decimal / 365.0
            sharpe_ratio = (
                (avg_daily_return - daily_rf) / daily_std
            ) * math.sqrt(252.0)

        total_return_pct = (
            ((portfolio_value / start_value) - 1.0) * 100.0
            if start_value > 0
            else 0.0
        )

        if start_value > 0 and total_days > 0:
            years = total_days / 365.0
            if years > 0 and portfolio_value > 0:
                cagr_pct = ((portfolio_value / start_value) ** (1 / years) - 1.0) * 100.0
            else:
                cagr_pct = 0.0
        else:
            cagr_pct = 0.0

        state_payload = {
            "state_id": 1,
            "portfolio_value": portfolio_value,
            "portfolio_peak": portfolio_peak,
            "start_value": start_value,
            "start_date": start_date,
            "total_days": total_days,
            "sum_return": sum_return,
            "sum_squared_diff": sum_squared,
            "risk_free_rate": rf_percent,
            "sharpe_ratio": sharpe_ratio,
            "cagr": cagr_pct,
            "max_drawdown": max_drawdown,
            "total_return": total_return_pct,
            "last_update": today,
        }

        stmt = pg_insert(portfolio_state).values(state_payload)
        update_cols = {
            k: getattr(stmt.excluded, k)
            for k in state_payload.keys()
            if k != "state_id"
        }
        conn.execute(stmt.on_conflict_do_update(index_elements=["state_id"], set_=update_cols))

        # Insert monthly checkpoint if needed
        year = today.year
        month = today.month
        existing_checkpoint = conn.execute(
            select(portfolio_checkpoints.c.id).where(
                portfolio_checkpoints.c.year == year,
                portfolio_checkpoints.c.month == month,
            )
        ).first()
        if not existing_checkpoint:
            conn.execute(
                pg_insert(portfolio_checkpoints).values(
                    {
                        "year": year,
                        "month": month,
                        "portfolio_value": portfolio_value,
                        "cagr": cagr_pct,
                        "sharpe": sharpe_ratio,
                        "drawdown": drawdown_pct,
                        "total_return": total_return_pct,
                    }
                )
            )

        _enforce_checkpoint_retention(conn, today, years=10)

        # Prepare upsert for portfolio_positions
        existing_rows_map = existing_positions
        now_ts = datetime.now(timezone.utc)
        upsert_rows = []

        for ticker, entry in entries.items():
            analysis_date = entry.get("analysis_date")
            existing_row = existing_rows_map.get(ticker)

            prev_analysis_dt = (
                _ensure_datetime(existing_row.get("analysis_date"))
                if existing_row
                else None
            )

            baseline_conv_score = (
                float(existing_row.get("conviction_baseline_score"))
                if existing_row and existing_row.get("conviction_baseline_score") is not None
                else None
            )
            baseline_conv_date = (
                _ensure_date(existing_row.get("conviction_baseline_date"))
                if existing_row
                else None
            )

            baseline_mos_value = (
                float(existing_row.get("mos_baseline_value"))
                if existing_row and existing_row.get("mos_baseline_value") is not None
                else None
            )
            baseline_mos_date = (
                _ensure_date(existing_row.get("mos_baseline_date"))
                if existing_row
                else None
            )

            current_conv = entry.get("conviction_score")
            current_mos = entry.get("margin_of_safety")

            if existing_row and prev_analysis_dt and analysis_date:
                delta_days = (analysis_date.date() - prev_analysis_dt.date()).days
                if delta_days >= 365 and existing_row.get("conviction_score") is not None:
                    baseline_conv_score = float(existing_row.get("conviction_score"))
                    baseline_conv_date = prev_analysis_dt.date()
                if delta_days >= 7 and existing_row.get("margin_of_safety") is not None:
                    baseline_mos_value = float(existing_row.get("margin_of_safety"))
                    baseline_mos_date = prev_analysis_dt.date()

            if baseline_conv_score is None and current_conv is not None:
                baseline_conv_score = float(current_conv)
                baseline_conv_date = analysis_date.date() if analysis_date else today
            if baseline_mos_value is None and current_mos is not None:
                baseline_mos_value = float(current_mos)
                baseline_mos_date = analysis_date.date() if analysis_date else today

            conv_change_pct = None
            if (
                current_conv is not None
                and baseline_conv_score not in (None, 0.0)
                and baseline_conv_score != 0.0
            ):
                conv_change_pct = (
                    (current_conv - baseline_conv_score) / abs(baseline_conv_score)
                ) * 100.0

            mos_change_pct = None
            if (
                current_mos is not None
                and baseline_mos_value not in (None, 0.0)
                and baseline_mos_value != 0.0
            ):
                mos_change_pct = (
                    (current_mos - baseline_mos_value) / abs(baseline_mos_value)
                ) * 100.0

            details = {
                "adjustments": entry.get("adjustments"),
                "notes": entry.get("notes"),
            }

            row_payload = {
                "ticker": ticker,
                "analysis_date": analysis_date,
                "conviction_score": current_conv,
                "conviction_baseline_score": baseline_conv_score,
                "conviction_baseline_date": baseline_conv_date,
                "conviction_change_pct": conv_change_pct,
                "margin_of_safety": current_mos,
                "mos_baseline_value": baseline_mos_value,
                "mos_baseline_date": baseline_mos_date,
                "mos_change_pct": mos_change_pct,
                "current_price": entry.get("current_price"),
                "quantity": entry.get("quantity"),
                "cost_basis": entry.get("cost_basis"),
                "current_value": entry.get("current_value"),
                "current_pct": entry.get("current_pct"),
                "target_pct": entry.get("target_pct_final"),
                "delta_pct": entry.get("delta_pct"),
                "total_return": entry.get("total_return"),
                "action_label": entry.get("action_label"),
                "action": entry.get("action"),
                "reallocation_flag": entry.get("reallocation_flag"),
                "details": details,
                "last_updated": now_ts,
            }
            upsert_rows.append(row_payload)

        if upsert_rows:
            stmt = pg_insert(portfolio_positions).values(upsert_rows)
            update_cols = {
                k: getattr(stmt.excluded, k)
                for k in upsert_rows[0].keys()
                if k != "ticker"
            }
            conn.execute(
                stmt.on_conflict_do_update(index_elements=["ticker"], set_=update_cols)
            )

    return {
        "portfolio_value": portfolio_value,
        "cash": cash_balance,
        "total_positions": len(entries),
    }
