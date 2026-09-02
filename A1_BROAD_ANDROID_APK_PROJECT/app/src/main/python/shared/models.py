from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

@dataclass(frozen=True)
class StrategyProfile:
    code: str
    name: str
    signal_body_min_pct: float = 0.0
    signal_body_max_pct: float = 1_000_000.0
    priority: int = 1
    enabled: bool = True

@dataclass(frozen=True)
class SetupFeatures:
    move_5m_pct: float
    rsi: float
    bb_touches_last_5: int
    bb_middle: float
    signal_body_pct: float = 0.0
    # Live order-flow fields. Historical candle tests leave these empty.
    ask_bid_ratio: Optional[float] = None
    delta_now: Optional[float] = None
    delta_peak: Optional[float] = None
    delta_divergence: bool = False
    # Compatibility fields retained only so existing paper state/log readers do not break.
    turnover_5m: float = 0.0
    higher_high_streak: int = 0
    mid_bb_distance_pct: float = 0.0
    volume_ratio_10: float = 0.0
    vwap_distance_pct: float = 0.0

@dataclass(frozen=True)
class ProfileMatch:
    profile: StrategyProfile
    features: SetupFeatures
    signal_index: int
    signal_time: Optional[str] = None
