"""Helpers to persist analysis results and document summaries.

This centralizes writes to `stock_analysis_results` and `document_summaries`.
"""

from datetime import datetime, timezone
from sqlalchemy.dialects.postgresql import insert as pg_insert


def upsert_analysis_result(db_engine, results_table, result: dict):
    """Upsert a single analysis result row into the results_table.

    result should be a dict with keys matching the table columns (เช่น ticker,
    ai_recommendation_summary, portfolio_directive, checklist_details ฯลฯ).
    """
    try:
        # Ensure last_updated-like timestamp if present
        result.setdefault("analysis_date", datetime.now(timezone.utc))

        stmt = pg_insert(results_table).values(result)
        # Use ticker as unique key (existing table marks ticker unique)
        update_cols = {
            k: getattr(stmt.excluded, k) for k in result.keys() if k != "ticker"
        }
        stmt = stmt.on_conflict_do_update(index_elements=["ticker"], set_=update_cols)

        with db_engine.connect() as conn:
            conn.execute(stmt)
            conn.commit()
        return True
    except Exception as e:
        raise


def save_document_summary(db_engine, document_table, filing_id, gemini_json):
    """Insert or update the document summary JSON for a filing_id."""
    try:
        stmt = pg_insert(document_table).values(
            {
                "filing_id": filing_id,
                "gemini_summary_json": gemini_json,
                "last_updated": datetime.now(timezone.utc),
            }
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["filing_id"],
            set_={
                "gemini_summary_json": stmt.excluded.gemini_summary_json,
                "last_updated": stmt.excluded.last_updated,
            },
        )
        with db_engine.connect() as conn:
            conn.execute(stmt)
            conn.commit()
        return True
    except Exception as e:
        raise
