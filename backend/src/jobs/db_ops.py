"""Database operation helpers extracted from daily_analysis_job.
Keep SQLAlchemy-specific logic in one place to simplify testing and reuse.
"""

from datetime import datetime, timezone
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy import select, delete, tuple_
from backend.src.database.models import system_status


def save_stock_profile(db_engine, stocks_table, stock_data: dict):
    try:
        stmt = pg_insert(stocks_table).values(stock_data)
        stmt = stmt.on_conflict_do_update(
            index_elements=["ticker"],
            set_={
                "company_name": stmt.excluded.company_name,
                "sector": stmt.excluded.sector,
                "industry": stmt.excluded.industry,
                "market_cap": stmt.excluded.market_cap,
                "logo_url": stmt.excluded.logo_url,
                "last_updated": stmt.excluded.last_updated,
            },
        )
        with db_engine.connect() as conn:
            conn.execute(stmt)
            conn.commit()
        return True
    except Exception:
        return False


def upsert_financial_records(db_engine, financial_data_table, records: list):
    if not records:
        return 0
    try:
        # Ensure each record has last_updated set to now (UTC) before inserting
        now = datetime.now(timezone.utc)
        for rec in records:
            if rec.get("last_updated") is None:
                rec["last_updated"] = now

        # Default annual periods to the year-end to keep keys consistent
        # REMOVED: Normalization to YYYY-12-31 causes issues with non-calendar fiscal years (e.g. NVDA Jan end).
        # We now keep the exact report date from the source.
        # if period_type == "A" and report_date:
        #     try:
        #         dt = pd.to_datetime(report_date)
        #         record["report_date"] = dt.replace(month=12, day=31).strftime("%Y-%m-%d")
        #     except Exception:
        #         pass

            rec["period_type"] = rec.get("period_type") or "A"

        # Gather keys that already exist so we only insert brand-new years
        keys_to_check = {
            (
                rec.get("ticker"),
                rec.get("report_date"),
                rec.get("period_type"),
            )
            for rec in records
            if rec.get("ticker") and rec.get("report_date") and rec.get("period_type")
        }

        with db_engine.connect() as conn:
            existing_keys = set()
            if keys_to_check:
                result = conn.execute(
                    select(
                        financial_data_table.c.ticker,
                        financial_data_table.c.report_date,
                        financial_data_table.c.period_type,
                    ).where(
                        tuple_(
                            financial_data_table.c.ticker,
                            financial_data_table.c.report_date,
                            financial_data_table.c.period_type,
                        ).in_(list(keys_to_check))
                    )
                )
                existing_keys = {
                    (row.ticker, row.report_date, row.period_type) for row in result
                }

            records_to_insert = []
            seen_new_keys = set()
            for rec in records:
                key = (
                    rec.get("ticker"),
                    rec.get("report_date"),
                    rec.get("period_type"),
                )
                if key[0] and key[1] and key[2]:
                    if key in existing_keys or key in seen_new_keys:
                        continue
                    seen_new_keys.add(key)
                records_to_insert.append(rec)

            if not records_to_insert:
                return 0

            stmt = pg_insert(financial_data_table).values(records_to_insert)
            stmt = stmt.on_conflict_do_nothing(
                index_elements=["ticker", "report_date", "period_type"]
            )
            result = conn.execute(stmt)
            conn.commit()
        return result.rowcount if result is not None else 0
    except Exception as e:
        raise e


def enforce_data_retention(
    db_engine, financial_data_table, ticker: str, limit: int = 15
):
    try:
        subquery = (
            select(financial_data_table.c.financial_data_id)
            .where(financial_data_table.c.ticker == ticker)
            .order_by(financial_data_table.c.report_date.desc())
            .limit(limit)
        ).scalar_subquery()

        delete_stmt = delete(financial_data_table).where(
            financial_data_table.c.ticker == ticker,
            financial_data_table.c.financial_data_id.not_in(subquery),
        )

        with db_engine.connect() as conn:
            result = conn.execute(delete_stmt)
            conn.commit()
        return result.rowcount
    except Exception as e:
        raise e


def set_system_status(db_engine, key: str, value: dict | None = None):
    """Upsert a system status key with optional JSON value and updated timestamp."""
    payload = value or {}
    try:
        stmt = pg_insert(system_status).values({"key": key, "value": payload})
        stmt = stmt.on_conflict_do_update(
            index_elements=[system_status.c.key],
            set_={
                "value": stmt.excluded.value,
                "last_updated": datetime.now(timezone.utc),
            },
        )
        with db_engine.connect() as conn:
            conn.execute(stmt)
            conn.commit()
        return True
    except Exception as e:
        # Don't crash pipeline for status write failures
        return False


def get_system_status(db_engine, key: str) -> dict | None:
    try:
        with db_engine.connect() as conn:
            result = conn.execute(
                select(system_status.c.value).where(system_status.c.key == key)
            ).scalar_one_or_none()
            return result
    except Exception:
        return None
