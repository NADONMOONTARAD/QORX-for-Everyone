"""Portfolio decision rules (public-edition ladders).

The public GitHub edition uses broad allocation bands instead of the fuller
private ladder set.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal, Optional


BUY_LADDER_FULL = [
    (30, 100, "L3"),
    (15, 50, "L2"),
    (0, 25, "L1"),
]

TRIM_TABLE_ELITE = [
    (0, 100, "Hold"),
    (-25, 75, "Trim -25%"),
    (-50, 50, "Trim -50%"),
    (-100, 25, "Maintain small position"),
    (-150, 0, "Exit"),
]

TRIM_TABLE_STRONG = [
    (0, 80, "Hold"),
    (-25, 60, "Trim -20%"),
    (-50, 35, "Trim -45%"),
    (-100, 15, "Trim to watch position"),
    (-150, 0, "Exit"),
]

TRIM_TABLE_OK = [
    (0, 50, "Hold"),
    (-10, 35, "Trim -15%"),
    (-25, 20, "Trim -30%"),
    (-50, 10, "Keep symbolic position"),
    (-100, 0, "Exit"),
]

REBALANCE_LEVELS = (
    (20, 30, "L2", 20),
    (10, 20, "L1", 10),
)


@dataclass
class PortfolioDirective:
    """Structured result for a single idea."""

    mode: Literal["buy", "trim", "exit", "hold"]
    target_pct: float
    label: str
    ladder_stage: str
    notes: str
    metadata: dict

    def to_dict(self) -> dict:
        payload = asdict(self)
        payload["metadata"] = dict(self.metadata or {})
        return payload


def _clamp(value: float, lower: float = 0.0, upper: float = 100.0) -> float:
    return max(lower, min(upper, value))


def conviction_floor(conviction: Optional[float]) -> float:
    conv = float(conviction or 0.0)
    if conv >= 80:
        return 50.0
    if conv >= 65:
        return 25.0
    return 0.0


def conviction_bucket(conv: float) -> str:
    if conv >= 80:
        return "high"
    if conv >= 65:
        return "medium"
    if conv >= 50:
        return "watch"
    return "exit"


def _choose_from_table(table: list[tuple[float, float, str]], value: float) -> tuple[float, str]:
    for threshold, target, stage in table:
        if value >= threshold:
            return target, stage
    # fallback to the smallest bucket
    last_target, _, stage = table[-1]
    return last_target, stage


def _buy_ladder_target(conviction: float, mos_pct: float) -> tuple[float, str]:
    base_target, stage = _choose_from_table(BUY_LADDER_FULL, mos_pct)
    if conviction >= 80:
        return base_target, stage
    if conviction >= 60:
        return round(base_target * 0.5, 2), f"{stage}_half"
    return 0.0, f"{stage}_blocked"


def _trim_ladder_target(conviction: float, mos_pct: float) -> tuple[float, str, str]:
    if conviction >= 85:
        target, stage = _choose_from_table(TRIM_TABLE_ELITE, mos_pct)
        return target, "trim", stage
    if conviction >= 70:
        target, stage = _choose_from_table(TRIM_TABLE_STRONG, mos_pct)
        return target, "trim", stage
    if conviction >= 60:
        target, stage = _choose_from_table(TRIM_TABLE_OK, mos_pct)
        return target, "trim", stage
    # conviction < 60 falls back to exit ladder handled elsewhere
    return 0.0, "exit", "Conv < 60"


def compute_portfolio_directive(
    conviction: Optional[float], margin_of_safety: Optional[float]
) -> PortfolioDirective:
    conv = float(conviction or 0.0)
    mos_pct = float(margin_of_safety or 0.0) * 100.0
    bucket = conviction_bucket(conv)
    notes = f"Conv {conv:.1f} ({bucket}), MoS {mos_pct:.1f}%"

    if conv < 50:
        return PortfolioDirective(
            mode="exit",
            target_pct=0.0,
            label="Close all positions within 5-10 business days",
            ladder_stage="exit_full",
            notes=notes,
            metadata={"bucket": bucket, "mos_pct": mos_pct},
        )
    if 50 <= conv <= 54:
        return PortfolioDirective(
            mode="exit",
            target_pct=25.0,
            label="Reduce to 25% holding (Exit ladder)",
            ladder_stage="exit_25",
            notes=notes,
            metadata={"bucket": bucket, "mos_pct": mos_pct},
        )
    if 55 <= conv <= 59:
        return PortfolioDirective(
            mode="exit",
            target_pct=50.0,
            label="Reduce to 50% holding (Exit ladder)",
            ladder_stage="exit_50",
            notes=notes,
            metadata={"bucket": bucket, "mos_pct": mos_pct},
        )

    if mos_pct < 0:
        target, mode, stage = _trim_ladder_target(conv, mos_pct)
        target = _clamp(target)
        return PortfolioDirective(
            mode="trim" if mode == "trim" else "exit",
            target_pct=target,
            label=f"{stage}",
            ladder_stage=stage,
            notes=notes,
            metadata={"bucket": bucket, "mos_pct": mos_pct},
        )

    target, stage = _buy_ladder_target(conv, mos_pct)
    target = _clamp(target)
    if target == 0:
        label = "Hold"
        mode = "hold"
    elif target >= 100:
        label = "Buy full allocation (100%)"
        mode = "buy"
    else:
        label = f"Buy up to {target:.1f}% of allocation"
        mode = "buy"

    return PortfolioDirective(
        mode=mode,
        target_pct=target,
        label=label,
        ladder_stage=stage,
        notes=notes,
        metadata={"bucket": bucket, "mos_pct": mos_pct},
    )


def determine_reallocation_level(delta_conv: float, delta_mos: float) -> Optional[tuple[str, float]]:
    """
    Returns (level_label, trim_pct) if the delta meets one of the reallocation gates.
    trim_pct is expressed in percentage points to trim from the old holding.
    """
    for conv_gate, mos_gate, label, trim_pct in REBALANCE_LEVELS:
        if delta_conv >= conv_gate and delta_mos >= mos_gate:
            return label, float(trim_pct)
    return None
