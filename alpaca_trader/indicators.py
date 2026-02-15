import pandas as pd
from ta.momentum import RSIIndicator
from ta.trend import SMAIndicator, MACD
from ta.volatility import BollingerBands

from alpaca_trader.config import (
    BollingerConfig,
    MACDConfig,
    RSIConfig,
    Settings,
    SMAConfig,
)


def compute_rsi(df: pd.DataFrame, config: RSIConfig) -> pd.DataFrame:
    """Add RSI value and signal columns to the DataFrame."""
    rsi = RSIIndicator(close=df["close"], window=config.period)
    df = df.copy()
    df["rsi"] = rsi.rsi()
    df["rsi_signal"] = None
    df.loc[df["rsi"] < config.oversold, "rsi_signal"] = "buy"
    df.loc[df["rsi"] > config.overbought, "rsi_signal"] = "sell"
    return df


def compute_sma_crossover(df: pd.DataFrame, config: SMAConfig) -> pd.DataFrame:
    """Add SMA short/long and crossover signal columns."""
    sma_short = SMAIndicator(close=df["close"], window=config.short_period)
    sma_long = SMAIndicator(close=df["close"], window=config.long_period)
    df = df.copy()
    df["sma_short"] = sma_short.sma_indicator()
    df["sma_long"] = sma_long.sma_indicator()

    df["sma_signal"] = None
    cross_up = (df["sma_short"] > df["sma_long"]) & (
        df["sma_short"].shift(1) <= df["sma_long"].shift(1)
    )
    cross_down = (df["sma_short"] < df["sma_long"]) & (
        df["sma_short"].shift(1) >= df["sma_long"].shift(1)
    )
    df.loc[cross_up, "sma_signal"] = "buy"
    df.loc[cross_down, "sma_signal"] = "sell"
    return df


def compute_macd(df: pd.DataFrame, config: MACDConfig) -> pd.DataFrame:
    """Add MACD line, signal line, histogram, and signal columns."""
    macd = MACD(
        close=df["close"],
        window_fast=config.fast_period,
        window_slow=config.slow_period,
        window_sign=config.signal_period,
    )
    df = df.copy()
    df["macd_line"] = macd.macd()
    df["macd_signal_line"] = macd.macd_signal()
    df["macd_histogram"] = macd.macd_diff()

    df["macd_signal"] = None
    cross_up = (df["macd_line"] > df["macd_signal_line"]) & (
        df["macd_line"].shift(1) <= df["macd_signal_line"].shift(1)
    )
    cross_down = (df["macd_line"] < df["macd_signal_line"]) & (
        df["macd_line"].shift(1) >= df["macd_signal_line"].shift(1)
    )
    df.loc[cross_up, "macd_signal"] = "buy"
    df.loc[cross_down, "macd_signal"] = "sell"
    return df


def compute_bollinger(df: pd.DataFrame, config: BollingerConfig) -> pd.DataFrame:
    """Add Bollinger Band values and signal columns."""
    bb = BollingerBands(
        close=df["close"],
        window=config.period,
        window_dev=config.std_dev,
    )
    df = df.copy()
    df["bb_upper"] = bb.bollinger_hband()
    df["bb_middle"] = bb.bollinger_mavg()
    df["bb_lower"] = bb.bollinger_lband()

    df["bb_signal"] = None
    df.loc[df["close"] <= df["bb_lower"], "bb_signal"] = "buy"
    df.loc[df["close"] >= df["bb_upper"], "bb_signal"] = "sell"
    return df


def compute_all(df: pd.DataFrame, settings: Settings) -> pd.DataFrame:
    """Run all enabled indicators on the DataFrame."""
    if settings.rsi.enabled:
        df = compute_rsi(df, settings.rsi)
    if settings.sma.enabled:
        df = compute_sma_crossover(df, settings.sma)
    if settings.macd.enabled:
        df = compute_macd(df, settings.macd)
    if settings.bollinger.enabled:
        df = compute_bollinger(df, settings.bollinger)
    return df
