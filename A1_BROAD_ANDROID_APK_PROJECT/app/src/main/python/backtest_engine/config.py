from dataclasses import dataclass,field
from pathlib import Path
from shared.a1_rules import (
    A1_MIN_MOVE_5M,A1_MAX_MOVE_5M,A1_MIN_RSI,A1_MIN_BB_TOUCHES,
    A1_STOP_RUPEES,A1_MAX_HOLDING_MINUTES,A1_TRADE_CAPITAL,
    A1_MARGIN_MULTIPLE,A1_CHARGES_PER_TRADE,A1_CUTOFF_HOUR,A1_CUTOFF_MINUTE,
)
ROOT=Path(__file__).resolve().parents[1]
@dataclass(frozen=True)
class StrategyRules:
    min_move_5m: float=A1_MIN_MOVE_5M
    max_move_5m: float=A1_MAX_MOVE_5M
    min_rsi: float=A1_MIN_RSI
    min_bb_touches: int=A1_MIN_BB_TOUCHES
    cutoff_hour:int=A1_CUTOFF_HOUR
    cutoff_minute:int=A1_CUTOFF_MINUTE
@dataclass(frozen=True)
class BacktestSettings:
    cache_dir:Path=ROOT/'cache'
    output_dir:Path=ROOT/'backtests'/'analytics'/'a1_live_parity'
    trade_capital:float=A1_TRADE_CAPITAL
    margin_multiple:float=A1_MARGIN_MULTIPLE
    stop_rupees:float=A1_STOP_RUPEES
    charges_per_trade:float=A1_CHARGES_PER_TRADE
    max_holding_minutes:int=A1_MAX_HOLDING_MINUTES
    rules:StrategyRules=field(default_factory=StrategyRules)
