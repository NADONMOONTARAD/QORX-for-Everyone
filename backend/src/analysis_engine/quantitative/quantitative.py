# backend/src/analysis_engine/quantitative/quantitative.py

import pandas as pd
import numpy as np


class QuantitativeAnalyzer:
    def __init__(self, financial_data_list_of_dicts):
        if not financial_data_list_of_dicts:
            self.df = pd.DataFrame()
        else:
            self.df = pd.DataFrame(financial_data_list_of_dicts)
            self._prepare_dataframe()

    def _prepare_dataframe(self):
        self.df["report_date"] = pd.to_datetime(self.df["report_date"])
        self.df.sort_values("report_date", inplace=True)
        numeric_cols = [
            "total_revenue",
            "net_income",
            "total_assets",
            "total_liabilities",
            "share_outstanding_diluted",
            "interest_bearing_debt",
            "operating_income",
            "income_tax_expense",
            "cash_flow_from_operations",
            "capital_expenditures",
            "gross_profit",
            "interest_expense",
            "premiums_earned",
            "losses_incurred",
            "selling_general_and_admin_expense",
            "policy_acquisition_costs",
            "dividends_paid",
            "shares_repurchased",
            "total_cost_of_buybacks",
            "avg_buyback_price",
        ]
        for col in numeric_cols:
            if col in self.df.columns:
                self.df[col] = pd.to_numeric(self.df[col], errors="coerce")

    def calculate_metrics(self):
        if self.df.empty:
            return pd.DataFrame()
        print("Calculating extensive quantitative metrics...")

        self.df["stockholders_equity"] = (
            self.df["total_assets"] - self.df["total_liabilities"]
        )
        self.df["debt_to_equity"] = (
            self.df["interest_bearing_debt"] / self.df["stockholders_equity"]
        )
        self.df["eps_diluted"] = (
            self.df["net_income"] / self.df["share_outstanding_diluted"]
        )

        avg_equity = (
            self.df["stockholders_equity"].shift(1) + self.df["stockholders_equity"]
        ) / 2
        self.df["roe"] = self.df["net_income"] / avg_equity

        self.df["free_cash_flow"] = (
            self.df["cash_flow_from_operations"] - self.df["capital_expenditures"]
        )

        tax_rate = (self.df["income_tax_expense"] / self.df["operating_income"]).fillna(
            0
        )
        nopat = self.df["operating_income"] * (1 - tax_rate)
        invested_capital = (
            self.df["interest_bearing_debt"] + self.df["stockholders_equity"]
        )
        self.df["roic"] = nopat / invested_capital

        self.df["gross_margin"] = self.df["gross_profit"] / self.df["total_revenue"]
        self.df["net_profit_margin"] = self.df["net_income"] / self.df["total_revenue"]
        self.df["fcf_margin"] = self.df["free_cash_flow"] / self.df["total_revenue"]

        self.df.set_index("report_date", inplace=True)
        year_gap = self.df.index.to_series().dt.year.diff()
        # --- FIX: Use robust growth calculation (diff / abs(prev)) to handle negative base values ---
        for col, growth_col in [
            ("total_revenue", "revenue_growth"),
            ("eps_diluted", "eps_growth_diluted"),
            ("free_cash_flow", "fcf_growth"),
        ]:
            if col in self.df.columns:
                self.df[growth_col] = self.df[col].diff() / self.df[col].shift(1).abs()
        if year_gap.notna().any():
            non_consecutive = year_gap > 1
            if non_consecutive.any():
                affected_index = non_consecutive.index[non_consecutive]
                for col in ("revenue_growth", "eps_growth_diluted", "fcf_growth"):
                    if col in self.df.columns:
                        # Drop growth jumps that stem from skipping fiscal years.
                        self.df.loc[affected_index, col] = np.nan
        self.df.reset_index(inplace=True)

        interest_expense_safe = self.df["interest_expense"].replace(0, np.nan)
        self.df["interest_coverage"] = (
            self.df["operating_income"] / interest_expense_safe
        )

        # --- SIMPLIFIED & CORRECTED COMBINED RATIO CALCULATION ---
        if "premiums_earned" in self.df.columns:
            # Fill missing expense components with 0 (แทน NaN).
            losses = self.df.get(
                "losses_incurred", pd.Series(0, index=self.df.index)
            ).fillna(0)
            
            # Additional safety fallback: if 'losses_incurred' is entirely 0, but we have 'cost_of_revenue'
            if losses.sum() == 0 and "cost_of_revenue" in self.df.columns:
                 losses = self.df.get("cost_of_revenue", pd.Series(0, index=self.df.index)).fillna(0)
                 
            gen_expenses = self.df.get(
                "selling_general_and_admin_expense", pd.Series(0, index=self.df.index)
            ).fillna(0)
            acq_costs = self.df.get(
                "policy_acquisition_costs", pd.Series(0, index=self.df.index)
            ).fillna(0)

            # Sum up all relevant losses and expenses safely.
            total_losses_and_expenses = losses + gen_expenses + acq_costs

            # Use 'premiums_earned' directly, as it already represents the NET value.
            net_premiums_earned = self.df["premiums_earned"]

            # Use np.where for safe division.
            self.df["combined_ratio"] = np.where(
                net_premiums_earned.notna() & (net_premiums_earned != 0),
                total_losses_and_expenses / net_premiums_earned,
                np.nan,
            )

        # --- DYNAMIC PAYOUT RATIO CALCULATION ---
        payout_series = pd.Series(dtype=float)
        if "net_income" in self.df.columns and "dividends_paid" in self.df.columns:
            dividends = self.df["dividends_paid"].abs()
            income = self.df["net_income"].replace(0, np.nan)
            payout_series = np.where(
                income > 0,
                (dividends / income).clip(0, 1.5),
                np.nan,
            )
            payout_series = pd.Series(payout_series, index=self.df.index)

        if not payout_series.empty:
            self.df["payout_ratio"] = payout_series

        self.df.replace([np.inf, -np.inf], np.nan, inplace=True)

        # 1. Define the core metrics that are always calculated.
        final_metric_columns = [
            "report_date",
            "roe",
            "roic",
            "debt_to_equity",
            "free_cash_flow",
            "eps_diluted",
            "revenue_growth",
            "eps_growth_diluted",
            "fcf_growth",
            "gross_margin",
            "net_profit_margin",
            "fcf_margin",
            "interest_coverage",
        ]

        # 2. Conditionally add the new metrics ONLY if they were successfully created.
        if "combined_ratio" in self.df.columns:
            final_metric_columns.append("combined_ratio")

        if "payout_ratio" in self.df.columns:
            final_metric_columns.append("payout_ratio")

        # 3. Select only the columns that actually exist in the DataFrame.
        metrics_to_update = self.df[final_metric_columns].copy()

        print("Metrics calculated successfully.")
        return metrics_to_update
