import pandas as pd


def get_financial_concept(report_dict, concepts):
    """
    Safely extracts a financial value from a report dictionary.
    Handles multiple possible concept names (XBRL tags).
    """
    for concept in concepts:
        value = report_dict.get(concept)
        if value is not None and str(value).strip() not in ["", "None"]:
            try:
                float_value = float(value)
                return int(float_value)
            except (ValueError, TypeError):
                continue
    return None


def safe_sum(values):
    """Returns the sum of all non-None values in the list. If all values are None, returns None."""
    nums = [v for v in values if v is not None]
    return sum(nums) if nums else None


def to_int(val):
    if val is None or pd.isna(val):
        return None
    try:
        return int(val)
    except (ValueError, TypeError):
        return None


def safe_subtract(*args):
    """
    Safely subtracts multiple numbers, handling None and invalid types.
    Example: safe_subtract(100, 20, 5) -> 75
    """
    nums = [float(x) for x in args if x is not None]
    if not nums:
        return None
    result = nums[0]
    for n in nums[1:]:
        result -= n
    return result
