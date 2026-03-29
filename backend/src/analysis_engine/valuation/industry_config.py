"""Transparent public-edition DCF configuration.

This GitHub version intentionally keeps the valuation routing simple and
classroom-friendly. The private thesis version can use richer heuristics, but
the published repo only exposes:

1. Broad sector defaults
2. A small set of structural industry exceptions that change model type

That keeps the teaching version understandable without exposing every custom
override from the original working model. The public repo therefore uses
standard educational heuristics, while the fuller thesis logic is available
separately on request.
"""

from typing import Any, Dict

# Default configuration used when neither sector nor industry matches.
DEFAULT_CONFIG: Dict[str, Any] = {
    "metric": "FCF",
    "base_mode": "LATEST",
    "growth_mode": "MEDIAN_3Y",
    "growth_cap": 0.15,
}

# Public edition: transparent sector-level baselines.
SECTOR_CONFIG: Dict[str, Dict[str, Any]] = {
    "Technology": {
        "metric": "FCF",
        "base_mode": "LATEST",
        "growth_mode": "MEDIAN_3Y",
        "growth_cap": 0.25,
    },
    "Communication Services": {
        "metric": "FCF",
        "base_mode": "LATEST",
        "growth_mode": "MEDIAN_3Y",
        "growth_cap": 0.20,
    },
    "Consumer Cyclical": {
        "metric": "FCF",
        "base_mode": "AVG_3Y",
        "growth_mode": "MEDIAN_3Y",
        "growth_cap": 0.15,
    },
    "Consumer Defensive": {
        "metric": "FCF",
        "base_mode": "AVG_3Y",
        "growth_mode": "MEDIAN_3Y",
        "growth_cap": 0.12,
    },
    "Healthcare": {
        "metric": "FCF",
        "base_mode": "AVG_3Y",
        "growth_mode": "MEDIAN_3Y",
        "growth_cap": 0.15,
    },
    "Financial Services": {
        "metric": "NET_INCOME",
        "base_mode": "AVG_5Y",
        "growth_mode": "MEDIAN_5Y",
        "growth_cap": 0.12,
    },
    "Real Estate": {
        "metric": "FCF",
        "base_mode": "LATEST",
        "growth_mode": "MEDIAN_5Y",
        "growth_cap": 0.10,
    },
    "Industrials": {
        "metric": "FCF",
        "base_mode": "AVG_5Y",
        "growth_mode": "MEDIAN_5Y",
        "growth_cap": 0.12,
    },
    "Basic Materials": {
        "metric": "FCF",
        "base_mode": "AVG_5Y",
        "growth_mode": "MEDIAN_5Y",
        "growth_cap": 0.10,
    },
    "Energy": {
        "metric": "FCF",
        "base_mode": "AVG_5Y",
        "growth_mode": "MEDIAN_5Y",
        "growth_cap": 0.10,
    },
    "Utilities": {
        "metric": "FCF",
        "base_mode": "AVG_5Y",
        "growth_mode": "MEDIAN_5Y",
        "growth_cap": 0.08,
    },
}

# Public edition: keep only the industry cases that need a distinct model route.
INDUSTRY_OVERRIDES: Dict[str, Dict[str, Any]] = {
    "Software - Infrastructure": {
        "metric": "HYPERSCALER_FCF",
        "base_mode": "LATEST",
        "growth_mode": "MEDIAN_3Y",
        "growth_cap": 0.25,
    },
    "Banks - Regional": {
        "metric": "NET_INCOME",
        "base_mode": "AVG_5Y",
        "growth_mode": "MEDIAN_5Y",
        "growth_cap": 0.10,
    },
    "Insurance - Life": {
        "metric": "NET_INCOME",
        "base_mode": "AVG_5Y",
        "growth_mode": "MEDIAN_5Y",
        "growth_cap": 0.10,
    },
    "Exchange Traded Fund": {
        "metric": "NET_INCOME",
        "base_mode": "AVG_3Y",
        "growth_mode": "MEDIAN_3Y",
        "growth_cap": 0.05,
    },
    "Shell Companies": {
        "metric": "FCF",
        "base_mode": "LATEST",
        "growth_mode": "MEDIAN_3Y",
        "growth_cap": 0.00,
    },
    "REIT - Industrial": {
        "metric": "FCF",
        "base_mode": "LATEST",
        "growth_mode": "MEDIAN_5Y",
        "growth_cap": 0.10,
    },
}

_METRIC_LABELS = {
    "FCF": "Free Cash Flow",
    "NET_INCOME": "Net Income",
    "HYPERSCALER_FCF": "Free Cash Flow (Hyperscaler Mode)",
}


def _normalize_key(value: str) -> str:
    return (value or "").strip().lower()


def get_dcf_config(sector: str, industry: str) -> dict:
    """Return a transparent DCF config for the public GitHub edition."""

    config = DEFAULT_CONFIG.copy()
    sector_key = _normalize_key(sector)
    industry_key = _normalize_key(industry)

    for sector_name, sector_config in SECTOR_CONFIG.items():
        if _normalize_key(sector_name) == sector_key:
            config.update(sector_config)
            break

    for industry_name, industry_config in INDUSTRY_OVERRIDES.items():
        if _normalize_key(industry_name) == industry_key:
            config.update(industry_config)
            break

    metric = config.get("metric", "FCF")
    config["base_metric_label"] = _METRIC_LABELS.get(metric, "Free Cash Flow")
    return config
