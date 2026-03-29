import math

import pandas as pd

from backend.src.analysis_engine.valuation.valuation_models import (
    _build_growth_curve,
    _calculate_average_base_and_growth,
    _calculate_growth_from_series,
    _calculate_median_growth_from_series,
)


def test_build_growth_curve_returns_expected_endpoints():
    curve = _build_growth_curve(0.20, 0.03, 4)

    assert len(curve) == 4
    assert math.isclose(float(curve[0]), 0.20, rel_tol=1e-9)
    assert math.isclose(float(curve[-1]), 0.03, rel_tol=1e-9)


def test_build_growth_curve_falls_back_to_linear_interpolation_for_zero_initial():
    curve = _build_growth_curve(0.0, 0.03, 3)

    assert len(curve) == 3
    assert math.isclose(float(curve[-1]), 0.03, rel_tol=1e-9)
    assert all(float(value) >= 0.0 for value in curve)


def test_calculate_growth_from_series_nulls_large_year_gaps():
    values = pd.Series([100.0, 150.0, 300.0])
    dates = pd.Series(["2021-12-31", "2022-12-31", "2024-12-31"])

    growth = _calculate_growth_from_series(values, dates)

    assert math.isclose(float(growth.iloc[1]), 0.5, rel_tol=1e-9)
    assert pd.isna(growth.iloc[2])


def test_calculate_median_growth_from_series_uses_recent_window():
    growth_series = pd.Series([0.10, 0.20, 0.30, 0.40])

    result = _calculate_median_growth_from_series(growth_series, 3)

    assert math.isclose(result, 0.30, rel_tol=1e-9)


def test_calculate_average_base_and_growth_returns_mean_and_label():
    series = pd.Series([10.0, 20.0, 30.0, 40.0])

    base_value, growth_rate, note = _calculate_average_base_and_growth(series, 4)

    assert math.isclose(float(base_value), 25.0, rel_tol=1e-9)
    assert growth_rate > 0
    assert note == "Avg 4Y"
