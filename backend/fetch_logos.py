"""
fetch_logos.py - ดึง URL โลโก้หุ้นจาก Financial Modeling Prep API (ฟรี)
แล้วบันทึกไว้ใน stocks.logo_url ใน database

Usage:
  python fetch_logos.py            # ดึงทุก ticker ที่ logo_url ยังว่าง
  python fetch_logos.py --all      # ดึงใหม่ทั้งหมด (เขียนทับ)
  python fetch_logos.py NVDA AAPL  # ระบุ ticker เองเลย
"""

import asyncio
import sys
import os
import httpx

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))

from src.database.db_connector import get_engine
from sqlalchemy import text

# Free endpoint – no API key needed, just ticker-based PNG URL
LOGO_API_BASE = "https://financialmodelingprep.com/image-stock"

async def check_logo_exists(client: httpx.AsyncClient, ticker: str) -> str | None:
    """Check if the logo URL is accessible and return it, else None."""
    url = f"{LOGO_API_BASE}/{ticker.upper()}.png"
    try:
        resp = await client.head(url, timeout=5, follow_redirects=True)
        if resp.status_code == 200 and "image" in resp.headers.get("content-type", ""):
            return url
    except Exception as e:
        print(f"  [WARN] {ticker}: {e}")
    return None


async def fetch_and_cache_logos(tickers: list[str], overwrite: bool = False):
    engine = get_engine()
    
    print(f"Fetching logos for {len(tickers)} tickers...")
    
    async with httpx.AsyncClient() as client:
        for ticker in tickers:
            logo_url = await check_logo_exists(client, ticker)
            if logo_url:
                with engine.begin() as conn:
                    conn.execute(
                        text("UPDATE stocks SET logo_url = :url WHERE ticker = :ticker"),
                        {"url": logo_url, "ticker": ticker},
                    )
                print(f"  [OK]   {ticker} -> {logo_url}")
            else:
                print(f"  [SKIP] {ticker}: no logo found")


def main():
    from sqlalchemy import text as sa_text

    engine = get_engine()
    force_all = "--all" in sys.argv
    
    # ถ้า pass ticker เองมาในอาร์กิวเมนต์
    explicit_tickers = [a for a in sys.argv[1:] if not a.startswith("--")]

    with engine.connect() as conn:
        if explicit_tickers:
            tickers = explicit_tickers
        elif force_all:
            rows = conn.execute(sa_text("SELECT ticker FROM stocks ORDER BY ticker")).fetchall()
            tickers = [r[0] for r in rows]
        else:
            # ดึงเฉพาะ ticker ที่ logo_url ยังว่าง
            rows = conn.execute(
                sa_text("SELECT ticker FROM stocks WHERE logo_url IS NULL OR logo_url = '' ORDER BY ticker")
            ).fetchall()
            tickers = [r[0] for r in rows]

    if not tickers:
        print("No tickers to update. Use --all to force refresh all.")
        return

    asyncio.run(fetch_and_cache_logos(tickers, overwrite=force_all))
    print(f"\nDone. Updated {len(tickers)} tickers.")


if __name__ == "__main__":
    main()
