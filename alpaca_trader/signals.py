import logging
from dataclasses import dataclass
from enum import Enum

import pandas as pd

from alpaca_trader.config import Settings

logger = logging.getLogger("alpaca_trader")


class Action(Enum):
    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"


@dataclass
class Signal:
    symbol: str
    action: Action
    strength: float  # 0.0 to 1.0 (fraction of indicators that agree)
    details: dict  # Per-indicator signal values for logging


def evaluate_signals(df: pd.DataFrame, symbol: str, settings: Settings) -> Signal:
    """
    Look at the last row of the DataFrame and aggregate indicator signals
    into a single BUY/SELL/HOLD decision based on the configured mode.
    """
    if df.empty:
        return Signal(symbol=symbol, action=Action.HOLD, strength=0.0, details={})

    latest = df.iloc[-1]

    # Collect signals from each enabled indicator
    signal_columns = []
    if settings.rsi.enabled:
        signal_columns.append("rsi_signal")
    if settings.sma.enabled:
        signal_columns.append("sma_signal")
    if settings.macd.enabled:
        signal_columns.append("macd_signal")
    if settings.bollinger.enabled:
        signal_columns.append("bb_signal")

    indicator_signals = {}
    for col in signal_columns:
        val = latest.get(col)
        # Convert NaN/None to None
        indicator_signals[col] = val if pd.notna(val) else None

    if not indicator_signals:
        return Signal(symbol=symbol, action=Action.HOLD, strength=0.0, details={})

    # Count votes
    buy_count = sum(1 for v in indicator_signals.values() if v == "buy")
    sell_count = sum(1 for v in indicator_signals.values() if v == "sell")
    total_enabled = len(indicator_signals)

    # Determine action based on aggregation mode
    mode = settings.signal.mode
    action = Action.HOLD

    if mode == "unanimous":
        if buy_count == total_enabled:
            action = Action.BUY
        elif sell_count == total_enabled:
            action = Action.SELL

    elif mode == "majority":
        min_agree = settings.signal.min_agree
        if buy_count >= min_agree and buy_count > sell_count:
            action = Action.BUY
        elif sell_count >= min_agree and sell_count > buy_count:
            action = Action.SELL

    elif mode == "any":
        if buy_count > 0 and sell_count == 0:
            action = Action.BUY
        elif sell_count > 0 and buy_count == 0:
            action = Action.SELL
        # Conflicting signals -> HOLD

    strength = max(buy_count, sell_count) / total_enabled if total_enabled > 0 else 0.0

    return Signal(
        symbol=symbol,
        action=action,
        strength=strength,
        details=indicator_signals,
    )
