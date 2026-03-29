# backend/src/analysis_engine/investment_checklist.py
import pandas as pd
import numpy as np
import json
from typing import Optional
import re
from scipy.stats import linregress
import warnings

from backend.src.api_clients.yfinance_client import YFinanceClient
from backend.src.api_clients.finnhub_client import FinnhubClient
from backend.src.analysis_engine.valuation import valuation_models
from backend.src.analysis_engine.valuation import dr_engine
from backend.src.analysis_engine.checklist import helpers, conviction
from backend.src.portfolio.rules import compute_portfolio_directive

warnings.simplefilter(action="ignore", category=FutureWarning)


class InvestmentChecklistAnalyzer:
    # Industry grouping relies on AI output parsed by checklist.classifier helpers.

    def get_latest_price(self) -> Optional[float]:
        """Fetch the latest spot price, preferring Finnhub with a yfinance fallback."""
        cache_key = f"spot_price::{self.ticker.upper()}"
        cached_price = self._cache_get(cache_key)
        if cached_price is not None:
            return cached_price

        price = self._safe_price_fetch(
            self.finnhub_client.get_latest_price, "Finnhub"
        )
        if price is None:
            price = self._safe_price_fetch(
                self.yfinance_client.get_current_price, "yfinance"
            )

        if price is not None:
            self._cache_set(cache_key, float(price))

        return price


    def __init__(
        self,
        ticker: str,
        quant_df: pd.DataFrame,
        qual_summary: dict,
        profile: dict,
        yfinance_client: YFinanceClient,
        finnhub_client: FinnhubClient,
        shared_cache: dict,
        heavy_asset_window=7,
        general_capex_window=5,
    ):  # (Feedback 3)
        self.ticker = ticker
        self.profile = profile
        self.qual_summary = qual_summary
        self.yfinance_client = yfinance_client
        self.finnhub_client = finnhub_client
        self.cache = shared_cache
        self.heavy_asset_window = heavy_asset_window
        self.general_capex_window = general_capex_window

        if quant_df.empty:
            self.quant_df = pd.DataFrame()
            self.latest_quant_data = pd.Series()
        else:
            self.quant_df = quant_df.copy()
            self.quant_df["report_date"] = pd.to_datetime(self.quant_df["report_date"])
            self.quant_df.sort_values("report_date", inplace=True)
            
            # --- Inject Owner Earnings (Modern Buffett) ---
            try:
                sector = (self.profile.get("sector") or "").strip().upper()
                industry = (self.profile.get("industry") or "").strip().upper()
                is_reit = sector == "REAL ESTATE" or "REIT" in industry or "REAL ESTATE INVESTMENT TRUST" in industry
                if sector == "FINANCIAL SERVICES" and not is_reit:
                    # Financials: Net Income is the best proxy
                    oe_series = pd.to_numeric(self.quant_df.get("net_income"), errors="coerce")
                else:
                    # General / REIT / Tech: CFO - Capex - SBC
                    cfo = pd.to_numeric(self.quant_df.get("cash_flow_from_operations"), errors="coerce").fillna(0)
                    capex = pd.to_numeric(self.quant_df.get("capital_expenditures"), errors="coerce").fillna(0).abs()
                    sbc = pd.to_numeric(self.quant_df.get("stock_based_compensation"), errors="coerce").fillna(0)
                    
                    oe_series = cfo - capex - sbc
                
                self.quant_df["owner_earnings"] = oe_series
                
                # Calculate Growth: (Curr - Prev) / Abs(Prev)
                self.quant_df["owner_earnings_growth"] = (
                    self.quant_df["owner_earnings"].diff() 
                    / self.quant_df["owner_earnings"].shift(1).abs()
                )
            except Exception as e:
                print(f"[Checklist] Failed to calc Owner Earnings: {e}")
                
            self.latest_quant_data = self.quant_df.iloc[-1]
        
        self.checklist_results = {}

    def get_strict_mrq(self, key: str) -> Optional[float]:
        """
        Retrieves the most recent (non-null) value for a given metric across all 
        history (Q and A), sorting by date descending.
        """
        if self.quant_df.empty or key not in self.quant_df.columns:
            return None
        
        # Sort full dataframe by report_date descending
        temp_df = self.quant_df.copy()
        temp_df["_rd"] = pd.to_datetime(temp_df.get("report_date"), errors="coerce")
        # Prefer Q (0) over A (1) if dates are identical
        temp_df["_rank"] = temp_df["period_type"].apply(lambda x: 0 if x == "Q" else 1)
        temp_df = temp_df.sort_values(by=["_rd", "_rank"], ascending=[False, True])
        
        for _, row in temp_df.iterrows():
            val = row.get(key)
            if val is not None and not pd.isna(val):
                return float(val)
        return None

    def _cache_get(self, key: str):
        if isinstance(self.cache, dict):
            return self.cache.get(key)
        return None

    def _cache_set(self, key: str, value) -> None:
        if not isinstance(self.cache, dict):
            return
        try:
            self.cache[key] = value
        except Exception:
            pass

    def _safe_price_fetch(self, fetch_callable, provider_label: str) -> Optional[float]:
        try:
            return fetch_callable(self.ticker)
        except Exception as exc:
            print(f"[Checklist] {provider_label} price fetch failed for {self.ticker}: {exc}")
            return None

    @staticmethod
    def _safe_float(value):
        try:
            return float(value) if value is not None else None
        except Exception:
            return None

    @staticmethod
    def _unwrap_ai_value(data):
        if isinstance(data, dict) and "value" in data:
            return data["value"]
        return data

    @staticmethod
    def _has_buyback_activity(shares_repurchased: Optional[float], total_cost: Optional[float]) -> bool:
        return bool(
            (shares_repurchased is not None and shares_repurchased > 0)
            or (total_cost is not None and total_cost > 0)
        )

    @staticmethod
    def _clamp_score(value: float, low: float = 0.0, high: float = 1.0) -> float:
        return max(low, min(float(value), high))

    def _get_latest_quant_rows(self):
        if self.quant_df.empty:
            return None, None, "quant_df_empty"

        try:
            latest_row = self.quant_df.iloc[-1]
        except Exception:
            return None, None, "missing_latest_row"

        prev_row = self.quant_df.iloc[-2] if len(self.quant_df) >= 2 else None
        return latest_row, prev_row, None

    def _get_share_outstanding_series(self) -> pd.Series:
        shares_series = self.quant_df.get("share_outstanding_diluted")
        if shares_series is None:
            return pd.Series(dtype=float)
        return shares_series.dropna()

    def _calculate_dilution_metrics(
        self, shares_series: pd.Series
    ) -> tuple[Optional[float], Optional[float]]:
        dilution_pct: Optional[float] = None
        prior_dilution_pct: Optional[float] = None

        if len(shares_series) >= 2:
            prev_shares = self._safe_float(shares_series.iloc[-2])
            latest_shares = self._safe_float(shares_series.iloc[-1])
            if prev_shares and latest_shares is not None:
                try:
                    dilution_pct = (latest_shares / prev_shares) - 1.0
                except Exception:
                    dilution_pct = None

        if len(shares_series) >= 3:
            prev_prev_shares = self._safe_float(shares_series.iloc[-3])
            prev_shares = self._safe_float(shares_series.iloc[-2])
            if prev_prev_shares and prev_shares is not None:
                try:
                    prior_dilution_pct = (prev_shares / prev_prev_shares) - 1.0
                except Exception:
                    prior_dilution_pct = None

        return dilution_pct, prior_dilution_pct

    @staticmethod
    def _calculate_price_to_iv_ratio(
        avg_price: Optional[float], intrinsic_value_prev: Optional[float]
    ) -> Optional[float]:
        if (
            avg_price
            and avg_price > 0
            and intrinsic_value_prev
            and intrinsic_value_prev > 0
        ):
            try:
                return avg_price / intrinsic_value_prev
            except Exception:
                return None
        return None

    @staticmethod
    def _score_buyback_from_ratio(
        price_to_iv_ratio: Optional[float],
    ) -> tuple[Optional[float], str]:
        if price_to_iv_ratio is None:
            return None, "ratio_unavailable"

        if price_to_iv_ratio <= 0.8:
            return 1.0, "buffett_ratio"
        if price_to_iv_ratio <= 1.0:
            return 0.85, "buffett_ratio"
        if price_to_iv_ratio <= 1.1:
            return 0.50, "buffett_ratio"
        if price_to_iv_ratio <= 1.3:
            return 0.25, "buffett_ratio"
        return 0.0, "buffett_ratio"

    @staticmethod
    def _score_buyback_from_dilution(
        dilution_pct: Optional[float],
        prior_dilution_pct: Optional[float],
        default_score: float,
    ) -> tuple[float, str]:
        if dilution_pct is None:
            return default_score, "fallback_no_dilution_data"

        two_year_decline = (
            prior_dilution_pct is not None
            and dilution_pct < -0.02
            and prior_dilution_pct < -0.02
        )

        if two_year_decline:
            return 1.0, "multi_year_share_reduction"
        if abs(dilution_pct) <= 0.02:
            return 0.5, "stable_share_count"
        if dilution_pct < -0.02:
            return 0.7, "single_year_share_reduction"
        return 0.0, "net_dilution"

    @staticmethod
    def _extract_cash_gt_debt_flag(quant_results: dict) -> bool:
        try:
            return bool(
                quant_results["financial_health"]["cash_gt_debt"]["pass"]
            )
        except (KeyError, TypeError):
            return False

    def _get_industry_group(self):
        """Return the YFinance Sector label (e.g., 'Technology', 'Financial Services')."""
        return (self.profile.get("sector") or "Unknown").strip()

    def _get_industry(self):
        """Return the YFinance Industry label (e.g., 'Software - Infrastructure')."""
        return (self.profile.get("industry") or "Unknown").strip()

    def _get_cyclical_tier(self):
        """Cyclical tier logic is now deprecated in favor of explicit Industry configurations. Returns None."""
        return None

    def _get_growth_window(self, series: pd.Series) -> int:
        """
        ใช้จำนวนข้อมูลที่สะอาดทั้งหมดเป็นหน้าต่างการคำนวณ growth
        เพื่อให้โมเดลใช้ประวัติเต็มที่เท่าที่มีในฐานข้อมูล
        """
        clean_series = series.dropna()
        available = len(clean_series)
        if available <= 0:
            return 0
        return available

    def _check(self, metric, condition, target):
        """Helper function to perform and format a single check."""
        # Delegate to helpers.check_latest_metric using latest_quant_data
        return helpers.check_latest_metric(
            self.latest_quant_data, metric, condition, target
        )

    def _run_part3_and_4_qualitative(self):
        """Part 3 & 4: Business & Management Quality"""
        # ในเวอร์ชันสมบูรณ์ เราจะส่ง Prompt ใหม่ๆ เพื่อถาม AI ละเอียดขึ้น
        # แต่ในตอนนี้ เราจะใช้ข้อมูลสรุปดิบจาก qual_summary ก่อน
        part3 = {
            "is_simple_and_understandable": {
                "pass": True,
                "note": self.qual_summary.get("business_model"),
            },
            "has_strong_economic_moat": {
                "pass": self.qual_summary.get("moat", "None") != "None",
                "note": self.qual_summary.get("moat"),
            },
        }
        part4 = {
            "management_is_rational": {
                "pass": True,
                "note": "Requires specific AI prompt on MD&A section",
            },
        }
        self.checklist_results["part3_business_quality"] = part3
        self.checklist_results["part4_management_quality"] = part4
        return part3, part4

    def _run_part6_business_risk(self):
        business_risks, _ = self._get_confident_value("business_risk_tags", 0)
        business_risks = business_risks or []

        is_zero_sum = "ZERO_SUM_GAME" in business_risks
        has_regulatory_risk = "REGULATORY_UNPREDICTABLE" in business_risks
        has_geopolitical_risk = "GEOPOLITICAL_RISK" in business_risks

        results = {
            "is_zero_sum_game": {
                "pass": not is_zero_sum,
                "note": (
                    "AI identified the industry as a potential zero-sum game."
                    if is_zero_sum
                    else "Industry appears to be a positive-sum game."
                ),
            },
            "has_unpredictable_regulatory_risk": {
                "pass": not (has_regulatory_risk or has_geopolitical_risk),
                "note": f"AI identified regulatory risk: {has_regulatory_risk}, geopolitical risk: {has_geopolitical_risk}",
            },
        }
        self.checklist_results["part6_business_risk_assessment"] = results
        return results

    def _calculate_moat_score(self) -> tuple[float, str]:
        return conviction.calculate_moat_score(self)

    # --- NEW: Conviction Score Calculation Engine ---
    # --- NEW: Conviction Score Calculation Engine ---
    def _calculate_conviction_score(
        self, moat_score: float, margin_of_safety: float, final_dr: float
    ) -> float:
        """Delegate to the conviction module implementing the Phase 1 /
        Phase 2 pillar structure (Quantitative, Qualitative, Ethical, Market
        Leadership, Regional Diversification)."""
        return conviction.calculate_conviction_score(
            self, moat_score, margin_of_safety, final_dr
        )

    def _evaluate_buyback_quality(self) -> tuple[float, dict]:
        """Compute Buffett-style buyback quality score (0..1) with debug context."""
        debug: dict = {}

        latest_row, prev_row, failure_reason = self._get_latest_quant_rows()
        if failure_reason:
            debug["reason"] = failure_reason
            # No data at all — neutral default
            return 0.5, debug

        shares_repurchased = self._safe_float(latest_row.get("shares_repurchased"))
        total_cost = self._safe_float(latest_row.get("total_cost_of_buybacks"))
        avg_price = self._safe_float(latest_row.get("avg_buyback_price"))
        report_date = latest_row.get("report_date")

        if shares_repurchased is not None and shares_repurchased < 0:
            shares_repurchased = abs(shares_repurchased)
        if total_cost is not None and total_cost < 0:
            total_cost = abs(total_cost)

        if (
            avg_price is None
            and shares_repurchased not in (None, 0)
            and total_cost not in (None, 0)
        ):
            try:
                avg_price = total_cost / shares_repurchased
            except Exception:
                avg_price = None

        iv_prev = (
            self._safe_float(prev_row.get("intrinsic_value_estimate"))
            if prev_row is not None
            else None
        )

        shares_series = self._get_share_outstanding_series()
        dilution_pct, prior_dilution_pct = self._calculate_dilution_metrics(
            shares_series
        )

        has_buyback_activity = self._has_buyback_activity(
            shares_repurchased, total_cost
        )
        price_to_iv_ratio = self._calculate_price_to_iv_ratio(avg_price, iv_prev)

        # Default score depends on whether the company actually spent money on buybacks:
        # - 0.0: total_cost_of_buybacks is zero/None → no buyback activity, no credit
        # - 0.5: buyback activity exists but avg_price or IV unavailable → fair neutral
        if not has_buyback_activity:
            default_score = 0.0
        else:
            default_score = 0.5

        score = default_score
        source = "no_buyback_activity" if not has_buyback_activity else "neutral_default"

        # Only score buyback quality if there was actual buyback activity
        if has_buyback_activity:
            ratio_score, ratio_source = self._score_buyback_from_ratio(price_to_iv_ratio)
            if ratio_score is not None:
                score, source = ratio_score, ratio_source
            else:
                score, source = self._score_buyback_from_dilution(
                    dilution_pct, prior_dilution_pct, default_score
                )

        # Override score if there is material dilution (regardless of buyback activity)
        if dilution_pct is not None and dilution_pct > 0.03:
            score = 0.0
            source = "dilution_penalty"

        score = self._clamp_score(score)

        debug.update(
            {
                "report_date": str(report_date) if report_date is not None else None,
                "shares_repurchased": shares_repurchased,
                "total_cost_of_buybacks": total_cost,
                "avg_buyback_price": avg_price,
                "intrinsic_value_prev": iv_prev,
                "price_to_iv_ratio": price_to_iv_ratio,
                "dilution_pct": dilution_pct,
                "prior_dilution_pct": prior_dilution_pct,
                "has_buyback_activity": bool(has_buyback_activity),
                "score": score,
                "source": source,
            }
        )

        return score, debug

    def _run_dcf_valuation(self, discount_rate=0.10, net_cash=0.0):
        # Delegate to new valuation module to keep code modular and maintain
        # exact original behavior/signature.
        return valuation_models._run_dcf_valuation(
            self, discount_rate, model_label="Standard FCF DCF", net_cash=net_cash
        )

    # --- REVISED: Main `run_full_analysis` orchestrator ---
    def run_full_analysis(self):
        """
        Executes the full, upgraded analysis and valuation workflow.
        """
        print("--- [Checklist] Starting Full Analysis Workflow ---")

        # --- Step 2: Single-Pass Quantitative Health Check ---
        quant_adj, quant_results = self._run_quantitative_health_check()
        self.checklist_results["quantitative_health_check"] = quant_results

        # --- Step 3: Confidently Extract AI Data ---
        moats_data, _ = self._get_confident_value("moats_identified", 0)
        moats_data = self._unwrap_ai_value(moats_data)
        self.qual_summary["moats_identified"] = moats_data or []

        moat_score, moat_rating = self._calculate_moat_score()
        print(f"[Checklist] Moat Score: {moat_score:.2f}, Rating: {moat_rating}")

        # --- Step 4: Run Updated Business Risk Check ---
        self._run_part6_business_risk()

        # --- Step 5: Pre-DCF Screening (Gate 2) ---
        # --- THIS IS THE FIX ---
        # เปลี่ยน Path จาก 'part2_red_flags' -> 'quantitative_health_check'
        pass_cash_gt_debt = self._extract_cash_gt_debt_flag(quant_results)
        has_severe_red_flags = not pass_cash_gt_debt
        # ---------------------

        final_dr = 0.10
        valuation_results = {}

        from backend.src.analysis_engine.checklist.val_dispatcher import is_fund_or_etf
        is_fund = is_fund_or_etf(self)

        if not is_fund and moat_score <= 1 and has_severe_red_flags:
            print(
                "[Checklist] Gate 2 FAIL: Minimal moat with severe red flags. Skipping DCF."
            )
            # ดึงราคาปัจจุบันเพื่อใส่ใน report
            current_price = self.get_latest_price()
            valuation_results = {
                "intrinsic_value_per_share": 0.0,
                "margin_of_safety": -1.0,
                "current_price": current_price,
                "note": "Moat ต่ำและเงินสดสุทธิแทบไม่เหลือเมื่อเทียบกับหนี้ ทำให้ข้ามการคำนวณ DCF.",
            }
        else:
            # --- Step 6: Full Dynamic Discount Rate Calculation ---
            final_dr = self._calculate_dynamic_discount_rate(moat_score, quant_adj)

            # --- Step 7: NEW - Run Valuation via Dispatcher ---
            # Use get_strict_mrq to ensure we get the latest non-null values (backup mechanism)
            cash = self.get_strict_mrq("cash_and_equivalents") or 0.0
            debt = self.get_strict_mrq("interest_bearing_debt") or 0.0
            
            # Use Sector/Industry to decide if Net Cash should be added
            sector = (self.profile.get("sector") or "").strip().upper()
            industry = (self.profile.get("industry") or "").strip().upper()
            
            is_reit = sector == "REAL ESTATE" or "REIT" in industry or "REAL ESTATE INVESTMENT TRUST" in industry
            
            net_cash = 0.0
            if sector != "FINANCIAL SERVICES" and not is_reit:
                net_cash = cash - debt
            
            valuation_results = self._select_and_run_valuation_model(final_dr, net_cash=net_cash)
            if valuation_results is None:
                valuation_results = {}
            try:
                iv = valuation_results.get("intrinsic_value_per_share")
                if iv in (None, 0, 0.0):
                    print(
                        f"[Valuation Debug] Intrinsic value is 0. Reason: {valuation_results.get('note')}"
                    )
            except Exception:
                pass

        # --- Step 8: Calculate Final Scores ---
        # คำนวณคะแนนสุขภาพจาก %pass ของ checklist
        total_checks = sum(
            1
            for part in self.checklist_results.values()
            if isinstance(part, dict)
            for cat in part.values()
            if isinstance(cat, dict)
            for res in cat.values()
            if isinstance(res, dict) and "pass" in res
        )
        # คำนวณคะแนนความน่าลงทุน (Conviction Score)
        # Ensure margin_of_safety is numeric (avoid None) before comparisons
        mos_raw = valuation_results.get("margin_of_safety")
        mos_value = mos_raw if mos_raw is not None else 0

        conviction_score = self._calculate_conviction_score(
            moat_score, mos_value, final_dr
        )
        print(f"[Checklist] Normalized Conviction Score: {conviction_score}/100")

        # Defer Phase 2 outputs until post_process_runner integration
        breakdown = self.checklist_results.get("conviction_breakdown")
        if isinstance(breakdown, dict):
            phase2_snapshot = breakdown.get("phase2")
            if phase2_snapshot is not None:
                breakdown["phase2_pending"] = phase2_snapshot
            breakdown["phase2"] = None

        if "conviction_phase2_score" in self.checklist_results:
            self.checklist_results["conviction_phase2_score_pending"] = (
                self.checklist_results["conviction_phase2_score"]
            )
            self.checklist_results["conviction_phase2_score"] = None

        # --- Step 8.1: Decide portfolio Action based on Conviction and MoS ---
        directive = compute_portfolio_directive(conviction_score, mos_value)
        directive_dict = directive.to_dict()
        target_pct = directive_dict.get("target_pct")
        if target_pct is not None:
            try:
                action_text = f"{directive_dict.get('label')} | Target {float(target_pct):.1f}%"
            except Exception:
                action_text = directive_dict.get("label")
        else:
            action_text = directive_dict.get("label") or "ถือ (Hold)"

        # --- Step 9: Assemble Final Output ---
        risks_data, _ = self._get_confident_value("risks", 0)
        risks_data = self._unwrap_ai_value(risks_data)
        if risks_data is None:
            risks_data = []

        intrinsic_reason = self._build_intrinsic_value_reason(
            valuation_results, moat_score, has_severe_red_flags
        )

        final_output = {
            "ticker": self.ticker,
            "analysis_date": pd.Timestamp.now(tz="UTC"),
            "moat_rating": moat_rating,
            "conviction_score": conviction_score,
            "key_risks": json.dumps(risks_data or []),
            "intrinsic_value_estimate": valuation_results.get(
                "intrinsic_value_per_share"
            ),
            "intrinsic_value_reason": intrinsic_reason,
            "ai_recommendation_summary": f"Conviction: {conviction_score}/100. MoS: {mos_value:.2%}",
            "ai_reasoning": f"DCF value is ${valuation_results.get('intrinsic_value_per_share')}, current price is ${valuation_results.get('current_price')}.",
            "portfolio_directive": directive_dict,
            "margin_of_safety": mos_raw,
            "current_price": valuation_results.get("current_price"),
            "checklist_details": self.checklist_results,
            "model_used": valuation_results.get("model_label"),
        }

        return final_output

    def _build_intrinsic_value_reason(
        self,
        valuation_results: dict | None,
        moat_score: float,
        has_severe_red_flags: bool,
    ) -> str | None:
        """Provide a human-readable reason when intrinsic value cannot be computed."""

        if not valuation_results:
            return "ระบบไม่สามารถคำนวณ intrinsic value ได้ เพราะโมดูลประเมินมูลค่าไม่คืนผลลัพธ์."

        intrinsic_value = valuation_results.get("intrinsic_value_per_share")
        try:
            # Treat very small positives (~0) as zero to avoid noise
            intrinsic_value = float(intrinsic_value) if intrinsic_value is not None else None
        except (TypeError, ValueError):
            intrinsic_value = None

        if intrinsic_value and intrinsic_value > 0:
            # Valid intrinsic value exists; no reason necessary
            return None

        reasons: list[str] = []

        raw_note = valuation_results.get("note")
        if raw_note:
            reasons.append(f"{raw_note}")

        if moat_score <= 1 and has_severe_red_flags:
            reasons.append(
                "Moat ต่ำและเงินสดสุทธิไม่ครอบคลุมหนี้ ทำให้ระบบเว้นการคำนวณ DCF."
            )



        # ลบข้อความซ้ำแบบรักษาลำดับ
        unique_reasons = list(dict.fromkeys(reason.strip() for reason in reasons if reason))
        return " | ".join(unique_reasons) if unique_reasons else None

    def _get_insider_scoring_thresholds(self) -> tuple[float, float]:
        return dr_engine._get_insider_scoring_thresholds(self)

    # --- STEP E: Qualitative Adjustment ---
    def _calculate_qual_adjustment(self, moat_score: float) -> float:
        adj, _ = dr_engine._calculate_qual_adjustment(self, moat_score)
        return adj

    # --- STEP A, F, G: Main Calculation Method ---
    def _calculate_dynamic_discount_rate(
        self, moat_score: float, quant_adj: float
    ) -> float:
        return dr_engine._calculate_dynamic_discount_rate(self, moat_score, quant_adj)

    def _get_confident_value(self, key: str, penalty_if_missing: float = 0.005):
        return helpers.get_confident_value(self.qual_summary, key, penalty_if_missing)

    def get_dynamic_threshold(self, weight_quant: float) -> float:
        """
        Return dynamic threshold for outlier detection based on company size.
        """
        return dr_engine.get_dynamic_threshold(self, weight_quant)

    def robust_metric(
        self, series: pd.Series, weight_quant: float, window: int | None = None
    ) -> float | None:
        return dr_engine.robust_metric(self, series, weight_quant, window)

    def _run_quantitative_health_check(self) -> tuple[float, dict]:
        """Delegate to checklist.quantitative.run_quantitative_health_check."""
        from backend.src.analysis_engine.checklist.quantitative import (
            run_quantitative_health_check,
        )

        return run_quantitative_health_check(self)

    def _select_and_run_valuation_model(self, discount_rate: float, net_cash: float = 0.0):
        """
        Dispatcher function that selects and runs the appropriate valuation model
        based on the company's industry group.
        """
        # Delegate to checklist.val_dispatcher to keep routing logic centralized
        from backend.src.analysis_engine.checklist.val_dispatcher import (
            select_and_run_valuation_model,
        )

        return select_and_run_valuation_model(self, discount_rate, net_cash=net_cash)

    def _run_insurance_valuation(self, discount_rate: float) -> dict:
        """
        Values an Insurance company using Net Income (Earnings Power).
        """
        return valuation_models._run_insurance_valuation(self, discount_rate)

    def _run_residual_income_model_for_banks(self, r: float) -> dict:
        """
        Values a bank using a conservative, ROE-driven Residual Income Model.
        """
        return valuation_models._run_residual_income_model_for_banks(self, r)

    def _run_conservative_fcfe_model(self, r: float) -> dict:
        """
        Legacy name map: Redirects to Insurance Valuation.
        """
        return valuation_models._run_insurance_valuation(self, r)

    def _run_dividend_discount_model(self, r: float) -> dict:
        return valuation_models._run_dividend_discount_model(self, r)

    def _run_shell_company_valuation(self) -> dict:
        """
        Special valuation for Shell Companies (returns 0 with custom note).
        """
        return valuation_models._run_shell_company_valuation(self)

    def _run_fund_nav_valuation(self, model_label: str = "Net Asset Value (NAV)") -> dict:
        """
        Special valuation for Funds and ETFs using NAV/Book Value.
        """
        return valuation_models._run_fund_nav_valuation(self, model_label)
