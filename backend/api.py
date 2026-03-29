# backend/api.py
import sys
import os
import contextlib
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select, insert, inspect
from pydantic import BaseModel, Field
from datetime import datetime, timezone, date

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from src.database.db_connector import DatabaseConnector
# นี่คือตัวแปรที่ใช้แทน "ตาราง"
from src.jobs.daily_analysis_job import stocks, financial_data, stock_analysis_results
from src.database.models import (
    portfolio_state,
    portfolio_checkpoints,
    portfolio_positions,
    transactions,
    product_segment_revenues,
    geo_segment_revenues,
    document_summaries,
    sec_filings_metadata,
    system_status,
)
from decimal import Decimal
from backend.src.portfolio.portfolio_engine import refresh_portfolio_snapshot

# --- START: Database Connection Refactor ---

# 1. สร้าง object สำหรับจัดการฐานข้อมูลและ engine เพียงครั้งเดียว
#    เพื่อใช้ซ้ำตลอดการทำงานของแอปพลิเคชัน
db = DatabaseConnector()
engine = db.get_engine()

# 2. สร้าง Lifespan Manager เพื่อจัดการการเชื่อมต่อและตัดการเชื่อมต่อของ engine
#    - @contextlib.asynccontextmanager เป็นวิธีของ Python ในการสร้างตัวจัดการ context
#    - FastAPI จะรันโค้ดก่อน `yield` เมื่อเซิร์ฟเวอร์เริ่มทำงาน
#    - และจะรันโค้ดหลัง `yield` เมื่อเซิร์ฟเวอร์ปิดตัวลง (เช่น ตอนรีสตาร์ท)
@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    # ก่อนแอปเริ่ม: ไม่ต้องทำอะไรเป็นพิเศษ เพราะเราสร้าง engine ไว้แล้ว
    print("FastAPI app is starting up...")
    yield
    # หลังแอปปิด: สั่งให้ engine ทำการปิด connection pool ทั้งหมด
    print("FastAPI app is shutting down, disposing database engine...")
    engine.dispose()

# --- END: Database Connection Refactor ---


class CashMutationRequest(BaseModel):
    amount: float = Field(..., gt=0, description="ยอดเงิน (USD)")

# ... (ส่วนที่เหลือของไฟล์เหมือนเดิม จนถึง app = FastAPI()) ...


def _to_native(value):
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {k: _to_native(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_to_native(v) for v in value]
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:
            return value
    return value


def _serialize_row(row):
    if not row:
        return None
    return {key: _to_native(val) for key, val in row.items()}


def _serialize_rows(rows):
    return [_serialize_row(row) for row in rows if row is not None]


def _latest_segment_payload(conn, table, ticker: str):
    try:
        inspector = inspect(conn)
        available_columns = {
            column["name"] for column in inspector.get_columns(table.name)
        }
    except Exception as e:
        print(f"Skipping segment payload for {table.name}: {e}")
        return None

    selectable_columns = [
        table.c.segment_group,
        table.c.segment_original_name,
        table.c.revenue_amount,
        table.c.period_type,
        table.c.report_date,
    ]
    # บางฐานข้อมูลเก่าอาจยังไม่มีคอลัมน์ raw/growth ชุดนี้
    optional_columns = []
    for attr_name in (
        "ai_confidence",
        "revenue_unit",
        "revenue_amount_raw",
        "revenue_growth_pct",
    ):
        if attr_name in available_columns:
            optional_columns.append(getattr(table.c, attr_name))

    rows = conn.execute(
        select(*selectable_columns, *optional_columns)
        .where(table.c.ticker == ticker)
        .order_by(table.c.report_date.desc())
    ).mappings().all()

    filtered = [
        row
        for row in rows
        if row.get("report_date") is not None
    ]
    if not filtered:
        return None

    annual_rows = [
        row for row in filtered if (row.get("period_type") or "").lower() == "annual"
    ]
    target_rows = annual_rows or filtered

    latest_date = max(row["report_date"] for row in target_rows)
    latest_rows = [
        row for row in target_rows if row["report_date"] == latest_date
    ]
    if not latest_rows:
        return None

    period_type = latest_rows[0].get("period_type")

    def _prepare(row):
        return {
            "segment_group": row.get("segment_group"),
            "segment_original_name": row.get("segment_original_name"),
            "revenue_amount": _to_native(row.get("revenue_amount")),
            "revenue_unit": row.get("revenue_unit"),
            "ai_confidence": _to_native(row.get("ai_confidence")),
            "revenue_amount_raw": _to_native(row.get("revenue_amount_raw")),
            "revenue_growth_pct": _to_native(row.get("revenue_growth_pct")),
        }

    return {
        "period": latest_date.isoformat(),
        "period_type": period_type,
        "rows": [_prepare(row) for row in latest_rows],
    }


def _fetch_dashboard_payload(conn):
    state_row = conn.execute(
        select(portfolio_state).where(portfolio_state.c.state_id == 1)
    ).mappings().first()

    checkpoints_rows = conn.execute(
        select(portfolio_checkpoints).order_by(
            portfolio_checkpoints.c.year,
            portfolio_checkpoints.c.month,
        )
    ).mappings().all()

    positions_rows = conn.execute(
        select(portfolio_positions).order_by(
            portfolio_positions.c.current_pct.desc()
        )
    ).mappings().all()

    return {
        "state": _serialize_row(state_row) or {},
        "checkpoints": _serialize_rows(checkpoints_rows),
        "positions": _serialize_rows(positions_rows),
    }


def _apply_cash_mutation(engine, *, amount: float, tx_type: str):
    now = datetime.now(timezone.utc)

    with engine.begin() as conn:
        current_cash_value = conn.execute(
            select(portfolio_positions.c.current_value).where(
                portfolio_positions.c.ticker == "CASH"
            )
        ).scalar()
        current_cash_value = float(current_cash_value or 0.0)

        if tx_type == "ADD_CASH":
            new_cash_value = current_cash_value + amount
        elif tx_type == "WITHDRAW":
            new_cash_value = current_cash_value - amount
            if new_cash_value < -1e-6:
                raise HTTPException(
                    status_code=400,
                    detail="ยอดเงินสดไม่เพียงพอสำหรับการถอน",
                )
        else:
            raise HTTPException(status_code=400, detail="Invalid cash mutation type")

        conn.execute(
            insert(transactions).values(
                {
                    "date": date.today(),
                    "ticker": "CASH",
                    "type": tx_type,
                    "amount": amount,
                    "price": None,
                    "quantity": None,
                    "cash_after": new_cash_value,
                    "created_at": now,
                }
            )
        )

    try:
        refresh_portfolio_snapshot(engine)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to refresh portfolio snapshot: {exc}",
        )

    with engine.connect() as conn:
        return _fetch_dashboard_payload(conn)

app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[],
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1):\d+",
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/api/stocks")
def get_all_stocks():
    db = DatabaseConnector()
    engine = db.get_engine()
    with engine.connect() as conn:
        stmt = select(stocks)
        result = conn.execute(stmt).mappings().all()
        return _serialize_rows(result)

@app.get("/api/stocks/{ticker}")
def get_stock_details(ticker: str):
    db = DatabaseConnector()
    engine = db.get_engine()
    with engine.connect() as conn:
        # --- เปลี่ยนชื่อตัวแปรที่เก็บ "ผลลัพธ์" ตรงนี้ ---
        stock_info_row = conn.execute(select(stocks).where(stocks.c.ticker == ticker)).mappings().first()
        
        analysis_result_row = conn.execute(
            select(stock_analysis_results)
            .where(stock_analysis_results.c.ticker == ticker)
            .order_by(stock_analysis_results.c.analysis_date.desc())
            .limit(1)
        ).mappings().first()
        
        financial_data_rows = conn.execute(
            select(financial_data)
            .where(financial_data.c.ticker == ticker)
            .order_by(financial_data.c.report_date.desc())
        ).mappings().all()

        product_breakdown = _latest_segment_payload(
            conn, product_segment_revenues, ticker
        )
        geo_breakdown = _latest_segment_payload(
            conn, geo_segment_revenues, ticker
        )
        portfolio_position_row = conn.execute(
            select(portfolio_positions).where(portfolio_positions.c.ticker == ticker)
        ).mappings().first()

        document_summary_json = conn.execute(
            select(document_summaries.c.gemini_summary_json)
            .select_from(
                document_summaries.join(
                    sec_filings_metadata,
                    document_summaries.c.filing_id == sec_filings_metadata.c.filing_id,
                )
            )
            .where(sec_filings_metadata.c.ticker == ticker)
            .order_by(sec_filings_metadata.c.filing_date.desc())
            .limit(1)
        ).scalar()

        sec_filings_rows = (
            conn.execute(
                select(
                    sec_filings_metadata.c.report_date,
                    sec_filings_metadata.c.filing_date,
                    sec_filings_metadata.c.form_type,
                    sec_filings_metadata.c.sec_url,
                )
                .where(
                    sec_filings_metadata.c.ticker == ticker,
                    sec_filings_metadata.c.form_type == "10-K",
                    sec_filings_metadata.c.sec_url.isnot(None),
                )
                .order_by(sec_filings_metadata.c.report_date.desc())
            )
            .mappings()
            .all()
        )

        status_rows = (
            conn.execute(
                select(system_status.c.key, system_status.c.value).where(
                    system_status.c.key.in_(
                        [f"status:{ticker}"]
                    )
                )
            )
            .mappings()
            .all()
        )
        status_map = {row["key"]: row["value"] for row in status_rows}

        return {
            "stockInfo": _serialize_row(stock_info_row),
            "analysisResult": _serialize_row(analysis_result_row),
            "financialData": _serialize_rows(financial_data_rows),
            "segmentRevenue": {
                "product": product_breakdown,
                "geo": geo_breakdown,
            },
            "portfolioPosition": _serialize_row(portfolio_position_row),
            "documentSummary": _to_native(document_summary_json)
            if document_summary_json is not None
            else None,
            "secFilings": [
                {
                    "report_date": (
                        row.report_date.isoformat() if row.report_date else None
                    ),
                    "filing_date": (
                        row.filing_date.isoformat() if row.filing_date else None
                    ),
                    "form_type": row.form_type,
                    "sec_url": row.sec_url,
                }
                for row in sec_filings_rows
            ],
            "systemStatus": {
                "status": _to_native(status_map.get(f"status:{ticker}")),
            },
        }


@app.get("/api/portfolio/dashboard")
def get_portfolio_dashboard():
    db = DatabaseConnector()
    engine = db.get_engine()

    with engine.connect() as conn:
        return _fetch_dashboard_payload(conn)


@app.post("/api/portfolio/deposit")
def create_portfolio_deposit(payload: CashMutationRequest):
    db = DatabaseConnector()
    engine = db.get_engine()

    amount = float(payload.amount)
    if amount <= 0:
        raise HTTPException(status_code=400, detail="Deposit amount must be positive")

    return _apply_cash_mutation(engine, amount=amount, tx_type="ADD_CASH")


@app.post("/api/portfolio/withdraw")
def create_portfolio_withdraw(payload: CashMutationRequest):
    db = DatabaseConnector()
    engine = db.get_engine()

    amount = float(payload.amount)
    if amount <= 0:
        raise HTTPException(status_code=400, detail="Withdraw amount must be positive")

    return _apply_cash_mutation(engine, amount=amount, tx_type="WITHDRAW")
