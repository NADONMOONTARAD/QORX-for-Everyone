# src/api_clients/finnhub_client.py

import os
import random
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import requests
from typing import List, Tuple
from dotenv import load_dotenv

from backend.src.utils.throttling import RateLimitedKeyPool

load_dotenv()


class FinnhubClient:
    """
    Client สำหรับเชื่อมต่อกับ Finnhub API
    """

    def __init__(self, *, min_interval_seconds: float = 1.0, max_retries: int = 4):
        keys = self._load_api_keys()
        if not keys:
            raise ValueError(
                "FINNHUB_API_KEY_# variables must be set in the environment."
            )
        self.base_url = "https://finnhub.io/api/v1"
        self._key_pool = RateLimitedKeyPool(
            keys,
            min_interval_seconds=min_interval_seconds,
            jitter_seconds=0.25,
            name="finnhub",
        )
        self._max_retries = max(1, int(max_retries))

    def _load_api_keys(self) -> List[str]:
        candidates: List[Tuple[int, str]] = []
        prefix = "FINNHUB_API_KEY_"
        prefix_len = len(prefix)
        for env_key, value in os.environ.items():
            if not env_key.startswith(prefix):
                continue
            suffix = env_key[prefix_len:]
            order = 0
            if suffix.isdigit():
                order = int(suffix)
            else:
                digits = "".join(ch for ch in suffix if ch.isdigit())
                order = int(digits) if digits else 0
            cleaned = (value or "").strip()
            if cleaned:
                candidates.append((order, cleaned))
        candidates.sort(key=lambda kv: kv[0])
        keys = [value for _, value in candidates if value]
        if not keys:
            fallback = (os.getenv("FINNHUB_API_KEY") or "").strip()
            if fallback:
                keys.append(fallback)
        return keys

    def _parse_retry_after(self, header_value: str | None) -> float | None:
        if not header_value:
            return None
        try:
            return float(header_value)
        except ValueError:
            try:
                dt = parsedate_to_datetime(header_value)
                if not dt:
                    return None
                return max(0.0, (dt - datetime.now(timezone.utc)).total_seconds())
            except Exception:
                return None
    def _request(self, endpoint, params=None):
        """Helper function to make rate-limited requests to the Finnhub API."""
        base_params = dict(params or {})
        attempt = 0
        while attempt < self._max_retries:
            api_key = self._key_pool.acquire()
            request_params = dict(base_params)
            request_params["token"] = api_key
            try:
                response = requests.get(
                    f"{self.base_url}/{endpoint}", params=request_params, timeout=40
                )
                if response.status_code == 429:
                    retry_after = self._parse_retry_after(
                        response.headers.get("Retry-After")
                    )
                    wait_time = min(30.0, retry_after or 1.0)
                    print(
                        f"Finnhub rate limited key. Waiting {wait_time:.2f}s before retry..."
                    )
                    self._key_pool.defer(api_key, wait_time)
                    time.sleep(wait_time)
                    attempt += 1
                    continue
                response.raise_for_status()
                if not response.text:
                    print(
                        f"Warning: Received empty response from Finnhub endpoint: {endpoint}"
                    )
                    return None
                return response.json()
            except requests.exceptions.RequestException as e:
                wait_time = min(20.0, (2**attempt) + random.uniform(0.5, 1.5))
                print(
                    f"Error fetching data from Finnhub (attempt {attempt + 1}/{self._max_retries}): {e}. Sleeping {wait_time:.2f}s"
                )
                self._key_pool.defer(api_key, wait_time)
                time.sleep(wait_time)
                attempt += 1
            finally:
                self._key_pool.release(api_key)
        print(f"Failed to fetch data from Finnhub endpoint '{endpoint}' after retries.")
        return None

    def get_quote(self, ticker: str):
        """Retrieve the latest quote snapshot from Finnhub."""
        return self._request("quote", {"symbol": ticker})

    def get_latest_price(self, ticker: str) -> float | None:
        """Convenience helper returning the most recent trade price from Finnhub."""
        quote = self.get_quote(ticker)
        if not isinstance(quote, dict):
            return None
        for key in ("c", "pc", "o"):
            value = quote.get(key)
            if isinstance(value, (int, float)):
                try:
                    return float(value)
                except Exception:
                    continue
        return None

    def get_company_profile(self, ticker):
        """ดึงข้อมูลโปรไฟล์ของบริษัท"""
        print(f"Fetching company profile for {ticker}...")
        return self._request("stock/profile2", {"symbol": ticker})

    def get_financials_as_reported(self, ticker, freq="annual"):
        """ดึงข้อมูลงบการเงิน (annual or quarterly)"""
        print(f"Fetching {freq} financials for {ticker}...")
        return self._request(
            "stock/financials-reported", {"symbol": ticker, "freq": freq}
        )

    def get_revenue_breakdown_segments(self, ticker):
        """
        ดึงข้อมูล Revenue by Segment/Geography จาก Finnhub.
        Endpoint: /stock/segments
        """
        print(f"Fetching revenue breakdown (segments) for {ticker}...")
        return self._request("stock/segments", {"symbol": ticker})

    def get_economic_data(self, code: str = "GDP"):
        """
        Fetches economic data from Finnhub.
        Default code is 'GDP' for Real GDP.
        """
        print(f"Fetching economic data for code: {code}...")
        # The endpoint requires a specific code, e.g., 'GDP' for US Real GDP.
        # The data is returned as a list of dictionaries, sorted by date.
        return self._request("economic/data", {"code": code})




