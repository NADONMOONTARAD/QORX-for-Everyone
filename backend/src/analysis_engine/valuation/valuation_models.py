"""Valuation model implementations.

These functions are designed to be called with the InvestmentChecklistAnalyzer instance
as the first argument (self).

MODELS IMPLEMENTED:
1. Unified FCF DCF (Standard & Hyperscaler)
2. Insurance Valuation (Net Income/Earnings Power)
3. Bank Residual Income (Stub)
"""

import pandas as pd
import numpy as np
from typing import Dict, Any, Optional, List
from datetime import datetime

from backend.src.analysis_engine.valuation import dr_engine


def _get_valuation_insights_container(analyzer) -> Optional[Dict[str, Any]]:
    checklist = getattr(analyzer, "checklist_results", None)
    if not isinstance(checklist, dict):
        return None
    return checklist.setdefault("valuation_insights", {})


def _to_native(value: Any):
    if isinstance(value, (np.generic,)):
        return float(value)
    if isinstance(value, np.ndarray):
        return [_to_native(v) for v in value.tolist()]
    if isinstance(value, list):
        return [_to_native(v) for v in value]
    if isinstance(value, dict):
        return {k: _to_native(v) for k, v in value.items()}
    return value


def _record_model_detail(analyzer, model_label: str, detail: Dict[str, Any]) -> None:
    insights = _get_valuation_insights_container(analyzer)
    if insights is None:
        return
    models = insights.setdefault("models", {})
    payload = _to_native(detail)
    payload["model_label"] = model_label
    models[model_label] = payload
    insights["model_used"] = model_label


def _build_growth_curve(initial: float, terminal: float, years: int) -> np.ndarray:
    """
    Builds a growth curve using Geometric Decay (Exponential/Log-Linear interpolation).
    Target: Smooth transition from Initial Growth to Terminal Growth (3%).
    """
    years = int(max(years, 1))

    try:
        initial_val = float(initial)
        terminal_val = float(terminal)
    except (TypeError, ValueError):
        return np.full(years, 0.03, dtype=float)

    if years <= 0:
        return np.array([], dtype=float)
    if years == 1:
        return np.array([terminal_val], dtype=float)

    if initial_val * terminal_val <= 0 or abs(initial_val) < 1e-4:
        return np.linspace(initial_val, terminal_val, years + 1)[1:]

    log_init = np.log(abs(initial_val))
    log_term = np.log(abs(terminal_val))
    log_steps = np.linspace(log_init, log_term, years)
    sign = 1 if initial_val > 0 else -1
    curve = sign * np.exp(log_steps)

    return curve


def _calculate_growth_from_series(
    values: Optional[pd.Series], report_dates: Optional[pd.Series]
) -> pd.Series:
    if values is None:
        return pd.Series(dtype=float)

    series = pd.to_numeric(values, errors="coerce")
    diff = series.diff()
    prev = series.shift(1).abs()  # Use ABS of previous value

    # Avoid division by zero
    growth = diff / prev
    growth.replace([np.inf, -np.inf], np.nan, inplace=True)

    if report_dates is not None:
        try:
            years = pd.to_datetime(report_dates, errors="coerce").dt.year
            year_gap = years.diff()
            if year_gap.notna().any():
                growth = growth.copy()
                growth[year_gap > 1] = np.nan
        except Exception:
            pass

    return growth


def _calculate_median_growth_from_series(growth_series: pd.Series, years: int) -> float:
    """
    Calculates the median growth rate from the last N valid periods.
    """
    valid = growth_series.dropna()
    if valid.empty:
        return 0.0
    
    # Take last N values
    subset = valid.tail(years)
    return float(subset.median())


def _calculate_average_base_and_growth(
    series: pd.Series, years: int
) -> tuple[float, float, str]:
    """
    Calculates Base Value (Average) and Growth Rate (Simple & Robust)
    using the "Simple & Robust" logic:
    - Base Value: Average of last N years.
    - Growth: (Avg_End - Avg_Start) / abs(Avg_Start)
      where Start and End are the first half and second half of the available period.
    """
    valid_series = series.dropna()
    count = len(valid_series)

    if count == 0:
        return 0.0, 0.0, "No data"

    # 1. Base Value: Average of last N years (or available)
    # The prompt says: "If year 5 or 4 or 3 missing... use just what is available"
    # So we take up to 'years' count from the end.
    window_series = valid_series.tail(years)
    base_value = window_series.mean()

    # 2. Growth Calculation: Simple & Robust
    # "Find Avg Start (e.g. Year 1-3)... Find Avg End (e.g. Year 3-5)... See % growth"
    # We will split the *entire* valid series into two halves to capture the long-term trend
    # or should we strictly use the N years window?
    # Usually trend analysis is better with more data.
    # But let's stick to the 'years' window if defined, or maybe full history?
    # The prompt implies using the window (e.g. "Avg 1-3" vs "Avg 3-5" for a 5 year avg).

    # Let's use the same window used for Base Value for consistency,
    growth_source = window_series
    g_count = len(growth_source)

    if g_count < 2:
        return base_value, 0.0, f"Avg ({g_count} yrs)"

    mid_point = g_count // 2
    # Ensure overlap if odd number?
    # e.g. 5 items: [0,1,2,3,4]. Mid=2.
    # Start: [0,1,2] (First 3). End: [2,3,4] (Last 3). Overlap at 2.
    # This matches "Avg 1-3" and "Avg 3-5" logic where year 3 is shared.

    if g_count % 2 != 0:
        # Odd
        start_slice = growth_source.iloc[: mid_point + 1]  # 0, 1, 2
        end_slice = growth_source.iloc[mid_point:]  # 2, 3, 4
    else:
        # Even: [0,1,2,3]. Mid=2.
        # Start: [0,1]. End: [2,3]. No overlap.
        start_slice = growth_source.iloc[:mid_point]
        end_slice = growth_source.iloc[mid_point:]

    avg_start = start_slice.mean()
    avg_end = end_slice.mean()

    if avg_start != 0 and not np.isnan(avg_start):
        # Precise Gap Calculation
        # Center of start slice (in 0-based index relative to growth_source)
        center_start = (len(start_slice) - 1) / 2.0
        # Center of end slice
        center_end = (g_count - 1) - ((len(end_slice) - 1) / 2.0)
        gap = max(1.0, center_end - center_start)

        if avg_start > 0 and avg_end > 0:
            # Use CAGR for positive values
            try:
                growth_rate = (avg_end / avg_start) ** (1 / gap) - 1
            except Exception:
                # Fallback if calculation fails
                growth_rate = ((avg_end - avg_start) / avg_start) / gap
        else:
            # Use Linear Annualized Growth for negative/mixed values
            total_growth = (avg_end - avg_start) / abs(avg_start)
            growth_rate = total_growth / gap
    else:
        growth_rate = 0.0

    return base_value, growth_rate, f"Avg {min(count, years)}Y"


def _get_quarterly_bridge(
    self, metric_name: str, last_annual_date, industry_mode: str = "STANDARD"
) -> tuple[float, str, str, Optional[pd.Timestamp]]:
    """
    Generic bridge function for any metric (FCF, Net Income).
    Returns: (Estimated TTM Value, Method Description, Source Label, Latest Date)
    """
    if last_annual_date is None:
        return None, "No Annual Date", "", None

    try:
        last_annual_ts = pd.Timestamp(last_annual_date)
    except Exception:
        return None, "Invalid Date Format", "", None

    # Fetch all quarterly data sorted by date
    df_q_all = self.quant_df[self.quant_df["period_type"] == "Q"].sort_values(
        "report_date"
    )

    if df_q_all.empty:
        return None, "No recent quarterly data found", "", None

    # If the latest quarterly report is not significantly newer than the last annual report 
    # (e.g., within 60 days, covering slight date misalignments for Q4 vs Annual), we don't need a bridge.
    latest_q_date_ts = pd.Timestamp(df_q_all["report_date"].iloc[-1])
    if latest_q_date_ts <= last_annual_ts + pd.Timedelta(days=60):
        return None, "Annual data is latest", "", None

    # Find the latest 8 quarters (to allow for nulls)
    df_q = df_q_all.tail(8).copy()

    # --- Metric Calculation Logic per Industry ---
    # Pre-fetch common columns for component-based calc (Hyperscaler/Standard)
    cfo = pd.to_numeric(df_q.get("cash_flow_from_operations"), errors="coerce")
    sbc = pd.to_numeric(df_q.get("stock_based_compensation"), errors="coerce")

    if industry_mode in ["INSURANCE", "BANK"]:
        vals = pd.to_numeric(df_q.get("net_income"), errors="coerce")
        vals = vals.dropna()
        series_q = vals

    elif industry_mode == "HYPERSCALER":
        capex = pd.to_numeric(df_q.get("capital_expenditures"), errors="coerce").abs()
        # Assume SBC is 0 if missing, don't drop the whole quarter
        sbc = sbc.fillna(0)
        temp = pd.DataFrame({"cfo": cfo, "capex": capex, "sbc": sbc})
        # Only drop if essential cash flow components are missing
        temp = temp.dropna(subset=["cfo", "capex"])
        if temp.empty:
            return None, "Insufficient Data for Hyperscaler FCF", "", None
        series_q = temp["cfo"] - temp["capex"] - temp["sbc"]

    else:  # STANDARD
        capex = pd.to_numeric(df_q.get("capital_expenditures"), errors="coerce").abs()
        sbc = sbc.fillna(0)
        temp = pd.DataFrame({"cfo": cfo, "capex": capex, "sbc": sbc})
        temp = temp.dropna(subset=["cfo", "capex"])
        if temp.empty:
            return None, "Insufficient Data for Standard FCF", "", None
        series_q = temp["cfo"] - temp["capex"] - temp["sbc"]

    # Only use the latest 4 non-null values for TTM, and get their dates safely
    # Build a DataFrame with value and date, drop nulls, take last 4
    ttm_df = (
        pd.DataFrame({"value": series_q, "report_date": df_q["report_date"]})
        .dropna(subset=["value"])
        .tail(4)
    )
    if len(ttm_df) < 4:
        return None, "Insufficient Quarterly Data (<4)", "", None
    ttm_est = ttm_df["value"].sum()
    method = "TTM"
    label = "TTM"
    used_dates = list(ttm_df["report_date"])
    latest_date = used_dates[-1] if used_dates else df_q["report_date"].max()
    
    latest_ts = None
    if latest_date is not None:
        try:
            latest_ts = pd.Timestamp(latest_date)
        except Exception:
            pass
            
    return ttm_est, method, label, latest_ts


def _generic_dcf_engine(
    self,
    series: pd.Series,
    metric_name: str,
    discount_rate: float,
    model_label: str,
    industry_bridge_mode: str = "STANDARD",
    base_mode: str = "LATEST",  # LATEST, AVG_3Y, AVG_5Y
    growth_mode: str = "ROBUST",  # ROBUST (default), MEDIAN_3Y, MEDIAN_5Y
    growth_cap: Optional[float] = None,
    net_cash: float = 0.0,
) -> dict:
    """
    Core engine that accepts any historical series (FCF, Net Income) and runs DCF.
    """
    if discount_rate is None:
        return {"intrinsic_value_per_share": 0.0, "note": "Missing discount_rate."}

    valid_series = series.dropna()
    if valid_series.empty or len(valid_series) < 3:
        return {
            "intrinsic_value_per_share": 0.0,
            "note": f"Insufficient {metric_name} history (<3 yrs).",
        }

    # --- TTM Calculation (Common for all modes) ---
    # We calculate TTM upfront so it can be used for Average modes (as the latest data point)
    # or for Latest mode (as the starting point).
    last_annual_val = float(valid_series.iloc[-1])
    last_date = valid_series.index[-1]

    ttm_val, ttm_note, src_label, ttm_date = _get_quarterly_bridge(
        self, metric_name, last_date, industry_bridge_mode
    )

    # --- Growth & Base Value Determination ---
    avg_line_value = None  # Value to draw the average line in frontend
    display_series = valid_series  # Default to annuals for history
    avg_bar_label = "Avg/Base"
    ttm_idx_ref = None  # Track TTM index for labeling

    # Combine Annuals + TTM for the calculations if TTM exists
    calc_series = valid_series.copy()
    if ttm_val is not None:
        # Ensure TTM index is strictly after last annual for Series operations
        t_idx = (
            ttm_date
            if (ttm_date and ttm_date > last_date)
            else last_date + pd.Timedelta(days=90)
        )
        calc_series[t_idx] = ttm_val
        display_series = calc_series  # Show TTM in history list
        ttm_idx_ref = t_idx

    # Initialize year_1_growth
    year_1_growth = 0.0
    current_val = 0.0
    
    # Calculate Growth Series first (needed for both modes)
    dates = calc_series.index.to_series()
    g_series = _calculate_growth_from_series(calc_series, dates)

    if base_mode.startswith("AVG"):
        # Extract years (AVG_3Y -> 3, AVG_5Y -> 5)
        try:
            years = int(base_mode.split("_")[1].replace("Y", ""))
        except:
            years = 3

        # Update Metric Name for Card Title (clean name without years)
        if "Historical" not in metric_name:
            metric_name = f"Historical {metric_name}"
        # Removed suffix per user request
        avg_bar_label = f"A({years}Y)"

        base_val, year_1_growth_raw, note_base = _calculate_average_base_and_growth(
            calc_series, years
        )
        current_val = base_val
        # avg_line_value = base_val # REMOVED per user request
        
        # Override Growth if specified
        if growth_mode != "ROBUST":
             if growth_mode == "MEDIAN_3Y":
                 year_1_growth = _calculate_median_growth_from_series(g_series, 3)
             elif growth_mode == "MEDIAN_5Y":
                 year_1_growth = _calculate_median_growth_from_series(g_series, 5)
             else:
                 year_1_growth = year_1_growth_raw
             
             note = f"Base: {base_mode}. Growth: {growth_mode}"
        else:
             year_1_growth = year_1_growth_raw
             note = f"Base: {base_mode}. Growth: ROBUST"

    else:  # LATEST / Standard
        current_val = ttm_val if ttm_val is not None else last_annual_val
        
        # Determine Growth
        if growth_mode != "ROBUST":
             if growth_mode == "MEDIAN_3Y":
                 year_1_growth = _calculate_median_growth_from_series(g_series, 3)
             elif growth_mode == "MEDIAN_5Y":
                 year_1_growth = _calculate_median_growth_from_series(g_series, 5)
             
             note = f"Base: {base_mode}. Growth: {growth_mode}"
             
        else:
            # Original Logic (Robust / Bridge)
            robust_growth = self.robust_metric(
                g_series.dropna(), dr_engine.DEFAULT_WEIGHT_QUANT
            )
            if robust_growth is None:
                # Fallback
                df_a = self.quant_df[self.quant_df["period_type"] == "A"].sort_values(
                    "report_date"
                )
                ni = pd.to_numeric(df_a.get("net_income"), errors="coerce")
                ni_g = _calculate_growth_from_series(ni, df_a.get("report_date")).dropna()
                robust_growth = self.robust_metric(ni_g, dr_engine.DEFAULT_WEIGHT_QUANT)

            if robust_growth is None:
                return {
                    "intrinsic_value_per_share": 0.0,
                    "note": "Cannot determine historical growth.",
                }

            robust_growth = float(robust_growth)

            if ttm_val is not None:
                if last_annual_val != 0:
                    bridge_growth = (ttm_val - last_annual_val) / abs(last_annual_val)
                else:
                    bridge_growth = 0.0
                year_1_growth = bridge_growth
                note = f"Base: {base_mode}. Growth: ROBUST (TTM Bridge)"
            else:
                year_1_growth = robust_growth / 2.0
                note = f"Base: {base_mode}. Growth: ROBUST (History)"
                current_val = last_annual_val * (1 + year_1_growth)

    # --- Cap Growth ---
    growth_cap_label = ""
    if growth_cap is not None:
        if year_1_growth > growth_cap:
            year_1_growth = growth_cap
            growth_cap_label = f" (Cap {int(growth_cap*100)}%)"
            note += growth_cap_label

    # --- Projections ---
    terminal_growth = 0.03
    projection_years = 10
    growth_rates = _build_growth_curve(year_1_growth, terminal_growth, projection_years)

    projections = []
    discounted_sum = 0

    # Use current_val (which is either Average or TTM) as the start
    curr = current_val

    for i, g in enumerate(growth_rates):
        year = i + 1
        val = curr * (1 + g)
        disc_val = val / ((1 + discount_rate) ** year)

        projections.append(
            {
                "year": year,
                "growth_rate": float(g),
                "value": float(val),
                "discounted_value": float(disc_val),
            }
        )
        discounted_sum += disc_val
        curr = val

    # --- Terminal Value ---
    if discount_rate <= terminal_growth:
        denom = max(0.01, discount_rate - terminal_growth)
    else:
        denom = discount_rate - terminal_growth

    tv_raw = (curr * (1 + terminal_growth)) / denom
    tv_disc = tv_raw / ((1 + discount_rate) ** projection_years)

    # --- Final Equity Value ---
    # Intrinsic Value = PV of Future Cash Flows + Net Cash (Cash - Interest Bearing Debt)
    total_val = discounted_sum + tv_disc + net_cash

    # Try to grab the most recent valid share count (Latest Date across Q and A)
    try:
        # Filter for rows with valid diluted shares
        shares_df = self.quant_df.dropna(subset=["share_outstanding_diluted"]).copy()
        
        if not shares_df.empty:
            # Sort by report_date descending
            # Secondary sort by period_type (Q before A) for ties on the same date
            # We map 'Q' to 0 and 'A' to 1 for sorting
            shares_df["period_rank"] = shares_df["period_type"].apply(lambda x: 0 if x == "Q" else 1)
            shares_df = shares_df.sort_values(by=["report_date", "period_rank"], ascending=[False, True])
            
            latest_record = shares_df.iloc[0]
            shares = float(latest_record["share_outstanding_diluted"])
        else:
            shares = None
    except Exception:
        shares = None

    price = self.get_latest_price()

    if not shares or pd.isna(shares) or shares <= 0:
        return {"intrinsic_value_per_share": 0.0, "note": "Missing shares."}

    per_share = total_val / shares
    mos = 1 - (price / per_share) if price and per_share > 0 else None
    
    # --- Implied Growth (Reverse PEG) ---
    implied_growth = None
    if industry_bridge_mode not in ["BANK", "INSURANCE", "REIT"] and price and shares and current_val > 0:
        try:
            oe_per_share = current_val / float(shares)
            if oe_per_share > 0:
                # Formula: PEG = 1 => Growth = P/E
                # Implied Growth = Price / OE_Per_Share
                # The result is a percentage in decimal (e.g., 40.0 means 4000%, 0.4 means 40%)
                # Wait, P/E of 20 means Growth of 20%.
                # P/E = 20.
                # If formula is Growth = P/E.
                # Then Growth is 20.
                # But in my system, growth of 0.20 is 20%.
                # So if P/E is 20, implied growth is 20 (not 0.20).
                # So I need to divide by 100 to get decimal?
                # User example: P/OE = 40.25 => Implied Growth = 40.25%.
                # My system uses 0.4025 for 40.25%.
                # So Implied Growth = (Price / OE) / 100.
                
                # ADJUSTED PRICE for Market Expectation:
                # We subtract Net Cash from the Price to see what growth is expected from OPERATIONS.
                adjusted_price = price - (net_cash / float(shares))
                if adjusted_price < 0:
                    adjusted_price = 0
                
                raw_pe = adjusted_price / oe_per_share
                implied_growth = raw_pe / 100.0
        except Exception:
            pass

    # --- History Recording ---
    hist_list = []
    # Re-calculate growth series for display (using the display_series which might include TTM)
    display_growth_series = _calculate_growth_from_series(
        display_series, display_series.index.to_series()
    )

    for dt, val in display_series.items():
        # Check if this is the TTM entry
        if ttm_idx_ref is not None and dt == ttm_idx_ref:
            label = "TTM"
        else:
            label = str(dt.year)

        item = {"year": label, "value": float(val)}
        if dt in display_growth_series.index:
            g_val = display_growth_series.loc[dt]
            if pd.notna(g_val):
                item["growth"] = float(g_val)
        hist_list.append(item)

    # Append Year 0 / DCF Base
    hist_list.append(
        {
            "year": "DCF Base",
            "value": float(current_val),
            "is_estimate": True,
            "growth": float(year_1_growth),
            "growth_cap_label": growth_cap_label,
            "note": "Starting Base Value",
        }
    )
    
    # Append Projection Years (Year 1 - Year 10)
    for p in projections:
        hist_list.append({
            "year": f"Year {p['year']}",
            "value": p["value"],
            "is_estimate": True,
            "is_projection": True, # Flag to distinguish from Base
            "growth": p["growth_rate"]
        })

    _record_model_detail(
        self,
        model_label,
        {
            "model_type": model_label,
            "base_metric": metric_name,
            "discount_rate": discount_rate,
            "terminal_growth": terminal_growth,
            "year_1_growth": year_1_growth,
            "implied_growth": implied_growth,
            "net_cash_adjustment": net_cash,
            "avg_line_value": None,
            "note": note,
            "fcf_history": hist_list,
            "projections": projections,
        },
    )


    return {
        "intrinsic_value_per_share": round(per_share, 2),
        "margin_of_safety": round(mos, 4) if mos else None,
        "current_price": float(price) if price else None,
        "model_label": model_label,
        "note": note,
    }


from backend.src.analysis_engine.valuation.industry_config import get_dcf_config

def _run_unified_fcf_valuation(
    self, discount_rate=None, starting_fcf=None, model_label="Unified DCF Model", net_cash=0.0
):
    """
    Standard DCF configured dynamically based on YFinance Sector and Industry.
    """
    sector = (self.profile.get("sector") or "").strip()
    industry = (self.profile.get("industry") or "").strip()
    # Public GitHub edition: use a small, transparent config map so students can
    # trace the valuation path without needing the original private heuristic table.
    config = get_dcf_config(sector, industry)

    df_a = (
        self.quant_df[self.quant_df["period_type"] == "A"]
        .sort_values("report_date")
        .copy()
    )
    if df_a.empty:
        return {"intrinsic_value_per_share": 0.0}
    df_a.set_index("report_date", inplace=True)

    metric_type = config.get("metric", "FCF")
    base_mode = config.get("base_mode", "LATEST")
    growth_mode = config.get("growth_mode", "MEDIAN_3Y")
    growth_cap = config.get("growth_cap", 0.25)
    base_metric_label = config.get("base_metric_label", "Free Cash Flow")

    cfo = pd.to_numeric(df_a.get("cash_flow_from_operations"), errors="coerce")
    capex_val = pd.to_numeric(df_a.get("capital_expenditures"), errors="coerce")
    capex = capex_val.abs()
    sbc = pd.to_numeric(df_a.get("stock_based_compensation"), errors="coerce").fillna(0)

    if metric_type == "NET_INCOME":
        series = pd.to_numeric(df_a.get("net_income"), errors="coerce")
        industry_mode = "INSURANCE" if "Insurance" in industry else "BANK"
    elif metric_type == "HYPERSCALER_FCF":
        series = cfo - capex - sbc
        industry_mode = "HYPERSCALER"
    else:
        series = cfo - capex - sbc
        industry_mode = "STANDARD"

    return _generic_dcf_engine(
        self, series, base_metric_label, discount_rate, model_label, industry_mode, base_mode, growth_mode, growth_cap, net_cash
    )


def _run_insurance_valuation(
    self, discount_rate: float, model_label: str = "Insurance Earnings DCF"
):
    """
    Insurance Valuation: Uses Net Income as the primary owner earnings proxy.
    Ignores FCF float noise.
    """
    df_a = (
        self.quant_df[self.quant_df["period_type"] == "A"]
        .sort_values("report_date")
        .copy()
    )
    if df_a.empty:
        return {"intrinsic_value_per_share": 0.0}
    df_a.set_index("report_date", inplace=True)

    # Use Net Income
    ni = pd.to_numeric(df_a.get("net_income"), errors="coerce")

    # INSURANCE: Average 5 Years. Growth: Median 5Y.
    base_mode = "AVG_5Y"
    growth_mode = "MEDIAN_5Y"
    
    try:
        from backend.src.analysis_engine.valuation.industry_config import get_dcf_config
        sector = (self.profile.get("sector") or "").strip()
        industry = (self.profile.get("industry") or "").strip()
        config = get_dcf_config(sector, industry)
        growth_cap = config.get("growth_cap", 0.15)
    except Exception:
        growth_cap = 0.15

    return _generic_dcf_engine(
        self, ni, "Net Income", discount_rate, model_label, "INSURANCE", base_mode, growth_mode, growth_cap
    )


def _run_bank_valuation(
    self, discount_rate: float, model_label: str = "Bank Earnings Power"
):
    """
    Bank Valuation (Buffett Style):
    หลักการ:
    1. ไม่ใช้ CFO (Cash Flow from Operations) เพราะเงินฝากเข้าจะทำให้ CFO บวมเกินจริง
       แต่เงินฝากคือหนี้สิน ไม่ใช่รายได้
    2. ใช้ Net Income เป็นตัวแทนของ Owner Earnings โดยตรง เพราะ CapEx ธนาคารต่ำ
    3. ธนาคารที่ดีต้องมีกำไรสม่ำเสมอ (Consistent Earnings Power)
    """
    # ดึงข้อมูลรายปี (Annual)
    df_a = (
        self.quant_df[self.quant_df["period_type"] == "A"]
        .sort_values("report_date")
        .copy()
    )
    if df_a.empty:
        return {"intrinsic_value_per_share": 0.0, "note": "No Annual Data"}

    df_a.set_index("report_date", inplace=True)

    # ใช้ Net Income เป็น Proxy ของ Free Cash Flow
    ni = pd.to_numeric(df_a.get("net_income"), errors="coerce")

    # ตรวจสอบคุณภาพกำไรเบื้องต้น (Buffett ชอบธนาคารที่กำไรไม่ผันผวนจากรายการพิเศษ)
    # หาก Net Income เป็นลบ หรือ ขาดหายไปเยอะ engine จะจัดการ cut off ให้เอง

    # BANK: Average 5 Years. Growth: Median 5Y.
    base_mode = "AVG_5Y"
    growth_mode = "MEDIAN_5Y"

    # เรียกใช้ Generic Engine โดยระบุโหมดเป็น "BANK"
    return _generic_dcf_engine(
        self,
        series=ni,
        metric_name="Net Income (Bank Proxy)",
        discount_rate=discount_rate,
        model_label=model_label,
        industry_bridge_mode="BANK",
        base_mode=base_mode,
        growth_mode=growth_mode,
    )


# --- Legacy Wrappers / Router ---


def _run_dcf_valuation(
    self, discount_rate=None, starting_oe=None, model_label="Standard FCF DCF", net_cash=0.0
):
    return _run_unified_fcf_valuation(self, discount_rate, starting_oe, model_label, net_cash)


def _run_conservative_fcfe_model(self, r: float) -> dict:
    # Map old insurer call to new insurance model
    return _run_insurance_valuation(self, r)


def _run_residual_income_model_for_banks(self, r: float) -> dict:
    # เปลี่ยนจาก Stub เป็นการเรียกใช้ Bank Valuation ของจริง
    # ถ้า r (Discount Rate) ไม่ถูกส่งมา ให้ใช้ค่า Default ที่ Conservative สำหรับธนาคาร (เช่น 10-12%)
    eff_r = r if r is not None else 0.10
    return _run_bank_valuation(
        self, discount_rate=eff_r, model_label="Bank Earnings DCF (Buffett)"
    )


def _run_dividend_discount_model(self, r: float) -> dict:
    return {"intrinsic_value_per_share": 0.0, "note": "DDM Not Implemented"}


def _run_shell_company_valuation(self) -> dict:
    """
    Returns 0 for Shell Companies with a specific warning.
    """
    price = self.get_latest_price()
    return {
        "intrinsic_value_per_share": 0.0,
        "margin_of_safety": None,
        "current_price": float(price) if price else None,
        "model_label": "Shell Company (No DCF)",
        "note": "ไม่สามารถประเมินมูลค่าด้วย DCF ได้ เนื่องจากเป็นบริษัทที่ไม่มีการดำเนินงานธุรกิจ (Blank Check Company)",
    }


def _run_fund_nav_valuation(self, model_label: str = "Net Asset Value (NAV)") -> dict:
    """
    Values Funds and ETFs using Book Value / Shares as a proxy for NAV.
    If NAV cannot be determined, returns 0 with a warning.
    """
    price = self.get_latest_price()
    # Try to calculate NAV per share.
    # 0. Try daily navPrice from YFinance info first
    nav_per_share = self.profile.get("navPrice")
    
    # 1. First look for net_asset_value if it exists
    if nav_per_share is None:
        nav_per_share = self.get_strict_mrq("net_asset_value")
    
    # 2. Try book_value_per_share
    if nav_per_share is None:
        nav_per_share = self.get_strict_mrq("book_value_per_share")
        
    # 3. Try equity / shares
    if nav_per_share is None:
        equity = self.get_strict_mrq("total_stockholder_equity")
        if equity is None:
            assets = self.get_strict_mrq("total_assets")
            liabs = self.get_strict_mrq("total_liabilities")
            if assets and liabs:
                equity = assets - liabs

        shares = self.get_strict_mrq("share_outstanding_diluted") or self.get_strict_mrq("share_outstanding_basic")
        if equity and shares and shares > 0:
            nav_per_share = equity / shares

    if nav_per_share is None or nav_per_share <= 0:
        return {
            "intrinsic_value_per_share": 0.0,
            "margin_of_safety": None,
            "current_price": float(price) if price else None,
            "model_label": model_label,
            "note": "ไม่สามารถประเมินมูลค่าด้วย NAV ได้ เนื่องจากไม่พบหน้าตักสินทรัพย์สุทธิที่เพียงพอ",
        }
    
    per_share = float(nav_per_share)
    mos = 1 - (price / per_share) if price and per_share > 0 else None
    
    _record_model_detail(
        self,
        model_label,
        {
            "model_type": model_label,
            "base_metric": "Net Asset Value",
            "nav_per_share": per_share,
            "note": "ประเมินมูลค่าด้วย NAV (Net Asset Value) หรือ Book Value",
            "fcf_history": [],
            "projections": [],
        },
    )

    return {
        "intrinsic_value_per_share": round(per_share, 2),
        "margin_of_safety": round(mos, 4) if mos else None,
        "current_price": float(price) if price else None,
        "model_label": model_label,
        "note": "ประเมินมูลค่าด้วย NAV (Net Asset Value)",
    }

