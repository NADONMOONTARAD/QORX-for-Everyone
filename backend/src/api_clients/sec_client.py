# src/api_clients/sec_client.py

import os
import requests
from dotenv import load_dotenv
from backend.src.utils.throttling import SlidingWindowRateLimiter

load_dotenv()

class SecClient:
    """
    Client สำหรับเชื่อมต่อกับ SEC EDGAR API
    """
    def __init__(self):
        self.user_agent = os.getenv("SEC_USER_AGENT")
        if not self.user_agent:
            raise ValueError("SEC_USER_AGENT is not set in the environment variables.")
        self.base_url = "https://data.sec.gov"
        self.headers = {'User-Agent': self.user_agent}
        self._limiter = SlidingWindowRateLimiter(max_calls=5, period_seconds=1.0, name='sec-edgar')
        self._tickers_cache = None

    def get_all_company_tickers(self):
        """
        ดึงรายการบริษัททั้งหมดจาก SEC (ticker + CIK)
        """
        if self._tickers_cache is not None:
            return self._tickers_cache

        url = "https://www.sec.gov/files/company_tickers.json"
        try:
            self._limiter.acquire()
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
            data = response.json()
            self._tickers_cache = data
            return data
        except requests.exceptions.RequestException as e:
            print(f"Error fetching company tickers from SEC: {e}")
            return None

    def get_company_submissions(self, cik):
        """
        ดึงข้อมูลการยื่นเอกสารทั้งหมดของบริษัทจาก CIK
        CIK ต้องเป็นตัวเลข 10 หลัก (เติม 0 ข้างหน้าถ้าจำเป็น)
        """
        cik_padded = str(cik).zfill(10)
        url = f"{self.base_url}/submissions/CIK{cik_padded}.json"
        
        print(f"Fetching submissions for CIK: {cik_padded}...")
        try:
            self._limiter.acquire()
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"Error fetching submissions from SEC for CIK {cik}: {e}")
            return None
    
    def get_cik_by_ticker(self, ticker):
        """
        แปลง Ticker เป็น CIK โดยใช้ข้อมูลโดยตรงจาก SEC
        """
        print(f"Fetching CIK for ticker: {ticker.upper()}...")
        all_tickers_data = self.get_all_company_tickers()
        if not all_tickers_data:
            return None

        # ข้อมูลที่ได้กลับมามีโครงสร้างเป็น { "0": {"cik_str": ..., "ticker": ..., "title": ...}, ...}
        # เราต้องวนลูปเพื่อหา ticker ที่ตรงกัน
        for company_info in all_tickers_data.values():
            if company_info.get('ticker') == ticker.upper():
                cik = str(company_info.get('cik_str')).zfill(10)
                print(f"Found CIK: {cik}")
                return cik
        
        print(f"CIK not found for ticker: {ticker}")
        return None
