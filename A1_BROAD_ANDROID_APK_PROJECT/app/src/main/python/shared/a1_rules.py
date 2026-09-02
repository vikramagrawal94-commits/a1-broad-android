from __future__ import annotations

# A1 selected setup - single source of truth for canonical candle-layer rules.
A1_MIN_MOVE_5M = 2.5
A1_MAX_MOVE_5M = float('inf')
A1_MIN_RSI = 90.0
A1_MAX_RSI = 98.0
A1_MIN_BB_TOUCHES = 2
A1_ALLOWED_BB_TOUCHES = frozenset((2, 3, 5))
A1_MIN_TURNOVER_5M = 20_000_000.0  # > Rs 2 crore
A1_MAX_TURNOVER_5M = 70_000_000.0  # < Rs 7 crore
A1_EXCLUDED_SIGNAL_HOURS = frozenset({11})  # no NEW signals 11:00-11:59 local exchange time

# Retained only for compatibility with older config/readers. They are NOT entry gates
# in these selected live builds.
A1_MIN_ASK_BID_IMBALANCE = 1.5
A1_DELTA_DIVERGENCE_DROP = 0.20

A1_STOP_RUPEES = 150.0
A1_MAX_HOLDING_MINUTES = 20
A1_TRADE_CAPITAL = 5000.0
A1_MARGIN_MULTIPLE = 5.0
A1_CHARGES_PER_TRADE = 50.0
A1_CUTOFF_HOUR = 15
A1_CUTOFF_MINUTE = 0


def bb_rule_label() -> str:
    values = '/'.join(str(x) for x in sorted(A1_ALLOWED_BB_TOUCHES))
    return f"upper-BB touches exactly {values} in last 5m"


def candle_filter_label() -> str:
    values = '/'.join(str(x) for x in sorted(A1_ALLOWED_BB_TOUCHES))
    return (
        f"5m move >{A1_MIN_MOVE_5M:.1f}% | "
        f"{A1_MIN_RSI:.0f}<RSI<{A1_MAX_RSI:.0f} | "
        f"upper-BB touches exactly {values} in last 5m | "
        f"Rs2Cr<5m turnover<Rs7Cr | exclude 11:00-11:59"
    )
