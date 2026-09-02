from __future__ import annotations
from datetime import datetime
from typing import Optional, Sequence

from .a1_rules import (
    A1_ALLOWED_BB_TOUCHES,
    A1_EXCLUDED_SIGNAL_HOURS,
    A1_MAX_RSI,
    A1_MAX_TURNOVER_5M,
    A1_MIN_TURNOVER_5M,
)
from shared.indicators import bollinger, rsi
from .models import ProfileMatch, SetupFeatures, StrategyProfile


def _timestamp(candle):
    value = getattr(candle, "timestamp", None)
    if value is not None:
        return value
    start_ms = getattr(candle, "start_ms", None)
    return datetime.fromtimestamp(start_ms / 1000) if start_ms is not None else None


def _setting(settings, name, live_name):
    return getattr(settings, name) if hasattr(settings, name) else getattr(settings, live_name)


def calculate_features(candles: Sequence, index: int, settings) -> Optional[SetupFeatures]:
    # Canonical A1 eligibility shared by historical backtest, live scanner and paper engine.
    # No wick/VWAP/RVOL/HH/liquidity/order-book/delta gates are added here.
    if index < 20 or index >= len(candles):
        return None

    c = candles[index]
    ts = _timestamp(c)
    if ts is not None and ts.hour in A1_EXCLUDED_SIGNAL_HOURS:
        return None

    base = candles[index - 5].close
    if base <= 0 or c.close <= 0:
        return None
    move = (c.close / base - 1.0) * 100.0
    if move <= _setting(settings, "min_move_5m", "a1_min_move_5m"):
        return None
    max_move = getattr(settings, "max_move_5m", getattr(settings, "a1_max_move_5m", float("inf")))
    if move > max_move:
        return None

    closes = [x.close for x in candles[: index + 1]]
    rv = rsi(closes, 14)
    if rv is None or rv <= _setting(settings, "min_rsi", "a1_min_rsi") or rv >= A1_MAX_RSI:
        return None

    touches = 0
    for j in range(index - 4, index + 1):
        bands = bollinger([x.close for x in candles[: j + 1]], 20, 2)
        if bands is None:
            return None
        if candles[j].high >= bands[1] or candles[j].close >= bands[1]:
            touches += 1
    if touches not in A1_ALLOWED_BB_TOUCHES:
        return None

    bands = bollinger(closes, 20, 2)
    if bands is None:
        return None

    turnover_5m = sum(
        max(0.0, float(x.close)) * max(0.0, float(x.volume))
        for x in candles[index - 4 : index + 1]
    )
    if turnover_5m <= A1_MIN_TURNOVER_5M or turnover_5m >= A1_MAX_TURNOVER_5M:
        return None

    body = abs(c.close - c.open) / c.close * 100.0 if c.close else 0.0
    return SetupFeatures(
        move_5m_pct=move,
        rsi=rv,
        bb_touches_last_5=touches,
        bb_middle=float(bands[0]),
        signal_body_pct=body,
        turnover_5m=float(turnover_5m),
    )


def evaluate_profile(candles, index, settings, profile: StrategyProfile):
    f = calculate_features(candles, index, settings)
    if f is None:
        return None
    ts = _timestamp(candles[index])
    return ProfileMatch(
        profile=profile,
        features=f,
        signal_index=index,
        signal_time=ts.isoformat() if ts else None,
    )


def evaluate_profiles(candles, index, settings, profiles):
    f = calculate_features(candles, index, settings)
    if f is None:
        return []
    ts = _timestamp(candles[index])
    return [
        ProfileMatch(profile=p, features=f, signal_index=index, signal_time=ts.isoformat() if ts else None)
        for p in profiles
        if p.enabled
    ]
