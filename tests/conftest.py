import pytest
import numpy as np
import pandas as pd

from alpaca_trader.config import (
    BollingerConfig,
    DataConfig,
    ExecutionConfig,
    MACDConfig,
    RSIConfig,
    ScheduleConfig,
    Settings,
    SignalConfig,
    SMAConfig,
)


@pytest.fixture
def sample_ohlcv():
    """Generate 100 rows of realistic OHLCV data."""
    np.random.seed(42)
    dates = pd.date_range(start="2025-01-01", periods=100, freq="D")
    close = 150 + np.cumsum(np.random.randn(100) * 2)
    return pd.DataFrame(
        {
            "open": close + np.random.randn(100) * 0.5,
            "high": close + abs(np.random.randn(100)),
            "low": close - abs(np.random.randn(100)),
            "close": close,
            "volume": np.random.randint(1_000_000, 10_000_000, 100),
        },
        index=dates,
    )


@pytest.fixture
def default_settings():
    """Return a Settings object with default values."""
    return Settings(
        rsi=RSIConfig(enabled=True, period=14, overbought=70, oversold=30),
        sma=SMAConfig(enabled=True, short_period=20, long_period=50),
        macd=MACDConfig(enabled=True, fast_period=12, slow_period=26, signal_period=9),
        bollinger=BollingerConfig(enabled=True, period=20, std_dev=2.0),
        signal=SignalConfig(mode="majority", min_agree=2),
        execution=ExecutionConfig(
            order_type="market",
            time_in_force="day",
            position_size_pct=5.0,
            max_positions=10,
            allow_short=False,
        ),
        data=DataConfig(timeframe="1Day", lookback_days=100),
        schedule=ScheduleConfig(
            enabled=False, interval_minutes=60, cron=None, market_hours_only=True
        ),
    )
