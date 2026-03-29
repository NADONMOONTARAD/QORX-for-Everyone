from __future__ import annotations

# backend/src/api_clients/yfinance_client.py

import yfinance as yf
import pandas as pd

from backend.src.utils.cache import TTLCache
from backend.src.utils.throttling import SlidingWindowRateLimiter


class YFinanceClient:
    def __init__(
        self,
        *,
        max_calls_per_minute: int = 6,
        financial_cache_hours: float = 6.0,
        price_cache_minutes: float = 10.0,
    ) -> None:
        max_calls = max(1, int(max_calls_per_minute))
        self._limiter = SlidingWindowRateLimiter(
            max_calls=max_calls,
            period_seconds=60.0,
            name="yfinance",
        )
        financial_ttl = max(300, int(financial_cache_hours * 3600))
        price_ttl = max(60, int(price_cache_minutes * 60))
        self._financial_cache: TTLCache[str, dict] = TTLCache(financial_ttl)
        self._info_cache: TTLCache[str, dict] = TTLCache(financial_ttl)
        self._price_cache: TTLCache[str, float] = TTLCache(price_ttl)
        self._treasury_cache: TTLCache[str, float] = TTLCache(price_ttl)
        self._dividend_cache: TTLCache[str, dict] = TTLCache(86400)

    def _throttle(self) -> None:
        self._limiter.acquire()

    def get_financial_statements(self, ticker: str):
        """Fetch income statement, balance sheet, and cash flow from yfinance."""
        symbol = (ticker or "").upper()
        cached = self._financial_cache.get(symbol)
        if cached is not None:
            return cached
        print(f"Attempting to fetch data from yfinance for {symbol}...")
        self._throttle()
        try:
            stock = yf.Ticker(symbol)
            income_stmt = stock.income_stmt
            balance_sheet = stock.balance_sheet
            cash_flow = stock.cashflow
            
            q_income_stmt = stock.quarterly_income_stmt
            q_balance_sheet = stock.quarterly_balance_sheet
            q_cash_flow = stock.quarterly_cashflow

            payload = {
                "incomeStatement": self._dataframe_to_records(income_stmt),
                "balanceSheet": self._dataframe_to_records(balance_sheet),
                "cashFlow": self._dataframe_to_records(cash_flow),
                "quarterlyIncomeStatement": self._dataframe_to_records(q_income_stmt),
                "quarterlyBalanceSheet": self._dataframe_to_records(q_balance_sheet),
                "quarterlyCashFlow": self._dataframe_to_records(q_cash_flow),
            }
            self._financial_cache.set(symbol, payload)
            return payload
        except Exception as e:
            print(f"Failed to get complete financial statements from yfinance: {e}")
            return None

    def _dataframe_to_records(self, df: pd.DataFrame):
        """Helper to convert a yfinance DataFrame into list-of-dicts."""
        if df is None or df.empty:
            return []
        df_melted = df.reset_index().melt(id_vars="index", var_name="date")
        df_pivoted = df_melted.pivot(index="date", columns="index", values="value")
        df_pivoted.reset_index(inplace=True)
        df_pivoted["date"] = pd.to_datetime(df_pivoted["date"]).dt.strftime("%Y-%m-%d")
        return df_pivoted.to_dict(orient="records")

    def get_company_info(self, ticker: str) -> dict:
        """Fetch the company information dictionary (.info) from yfinance."""
        symbol = (ticker or "").upper()
        cached = self._info_cache.get(symbol)
        if cached is not None:
            return cached
        print(f"Fetching company info from yfinance for {symbol}...")
        self._throttle()
        try:
            stock = yf.Ticker(symbol)
            info = stock.info or {}
            self._info_cache.set(symbol, info)
            return info
        except Exception as e:
            print(f"Could not fetch yfinance company info for {symbol}: {e}")
            return {}

    def get_current_price(self, ticker: str) -> float | None:
        """Fetch the most recent closing price for a ticker."""
        symbol = (ticker or "").upper()
        cached = self._price_cache.get(symbol)
        if cached is not None:
            return cached
        self._throttle()
        try:
            stock = yf.Ticker(symbol)
            history = stock.history(period="1d")
            if history.empty:
                return None
            price = float(history["Close"].iloc[-1])
            self._price_cache.set(symbol, price)
            return price
        except Exception as e:
            print(f"Could not fetch current price for {symbol}: {e}")
            return None

    def get_us_treasury_yield(self) -> float | None:
        """Fetch the current 10-Year US Treasury Yield (^TNX)."""
        cached = self._treasury_cache.get("^TNX")
        if cached is not None:
            return cached
        self._throttle()
        try:
            tnx = yf.Ticker("^TNX")
            history = tnx.history(period="5d")
            if history.empty:
                print("Could not fetch treasury yield history.")
                return None
            last_price = float(history["Close"].iloc[-1])
            rate = last_price / 100.0
            self._treasury_cache.set("^TNX", rate)
            return rate
        except Exception as e:
            print(f"Error fetching US Treasury Yield: {e}")
            return None

    def get_dividend_data(self, ticker: str) -> dict | None:
        """Fetch the latest DPS and 5-year CAGR of dividends."""
        symbol = (ticker or "").upper()
        cached = self._dividend_cache.get(symbol)
        if cached is not None:
            return cached
        self._throttle()
        try:
            stock = yf.Ticker(symbol)
            dividends = stock.dividends.resample("YE").sum()
            if len(dividends) < 2:
                return None
            d0 = dividends.iloc[-1]
            if d0 <= 0:
                return None
            if len(dividends) > 5:
                five_years_ago_dividend = dividends.iloc[-6]
                num_years = 5
            else:
                five_years_ago_dividend = dividends.iloc[0]
                num_years = max(1, len(dividends) - 1)
            if five_years_ago_dividend <= 0:
                growth_rate = 0.0
            else:
                growth_rate = (d0 / five_years_ago_dividend) ** (1 / num_years) - 1
                growth_rate = max(0.0, growth_rate)
            result = {"dps": float(d0), "growth_rate": float(growth_rate)}
            self._dividend_cache.set(symbol, result)
            return result
        except Exception as e:
            print(f"Error fetching dividend data for {symbol}: {e}")
            return None

    def get_insider_ownership(self, ticker: str) -> float | None:
        """Fetch % insider from Yahoo Finance major_holders."""
        symbol = (ticker or "").upper()
        self._throttle()
        try:
            stock = yf.Ticker(symbol)
            major_holders = stock.major_holders
            if major_holders is not None:
                try:
                    if hasattr(major_holders, "empty") and not major_holders.empty:
                        insider_fraction = major_holders.iloc[0, 0]
                        if insider_fraction is not None:
                            val = float(insider_fraction)
                            return val * 100.0 if val <= 1.0 else val
                except Exception:
                    try:
                        if len(major_holders) > 1:
                            insider_fraction = major_holders[1][0]
                            return float(insider_fraction) * 100.0
                    except Exception:
                        pass
            return None
        except Exception as e:
            print(f"Error fetching insider ownership from yfinance: {e}")
            return None
