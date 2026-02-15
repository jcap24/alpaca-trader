import pandas as pd
import numpy as np

from alpaca_trader.config import BollingerConfig, MACDConfig, RSIConfig, SMAConfig
from alpaca_trader.indicators import (
    compute_bollinger,
    compute_macd,
    compute_rsi,
    compute_sma_crossover,
    compute_all,
)


class TestRSI:
    def test_adds_columns(self, sample_ohlcv):
        config = RSIConfig(enabled=True, period=14, overbought=70, oversold=30)
        df = compute_rsi(sample_ohlcv, config)
        assert "rsi" in df.columns
        assert "rsi_signal" in df.columns

    def test_rsi_range(self, sample_ohlcv):
        config = RSIConfig(enabled=True, period=14, overbought=70, oversold=30)
        df = compute_rsi(sample_ohlcv, config)
        valid_rsi = df["rsi"].dropna()
        assert (valid_rsi >= 0).all()
        assert (valid_rsi <= 100).all()

    def test_buy_signal_when_oversold(self):
        """RSI should signal buy when value drops below oversold threshold."""
        # Create data that trends strongly downward to push RSI low
        close = pd.Series([100.0] * 5 + [100 - i * 3 for i in range(30)])
        df = pd.DataFrame({"close": close})
        config = RSIConfig(enabled=True, period=14, overbought=70, oversold=30)
        df = compute_rsi(df, config)
        # At least some rows should have buy signals if RSI drops below 30
        buy_rows = df[df["rsi_signal"] == "buy"]
        oversold_rows = df[df["rsi"] < 30].dropna()
        assert len(buy_rows) == len(oversold_rows)

    def test_does_not_modify_original(self, sample_ohlcv):
        config = RSIConfig(enabled=True, period=14, overbought=70, oversold=30)
        original_cols = set(sample_ohlcv.columns)
        compute_rsi(sample_ohlcv, config)
        assert set(sample_ohlcv.columns) == original_cols


class TestSMACrossover:
    def test_adds_columns(self, sample_ohlcv):
        config = SMAConfig(enabled=True, short_period=20, long_period=50)
        df = compute_sma_crossover(sample_ohlcv, config)
        assert "sma_short" in df.columns
        assert "sma_long" in df.columns
        assert "sma_signal" in df.columns

    def test_crossover_detection(self):
        """Manually construct a crossover and verify detection."""
        # Short SMA crosses above long SMA at index 5
        close = pd.Series([10, 10, 10, 10, 10, 20, 25, 30, 35, 40] * 6)
        df = pd.DataFrame({"close": close})
        config = SMAConfig(enabled=True, short_period=3, long_period=5)
        df = compute_sma_crossover(df, config)
        signals = df["sma_signal"].dropna()
        assert "buy" in signals.values or "sell" in signals.values


class TestMACD:
    def test_adds_columns(self, sample_ohlcv):
        config = MACDConfig(enabled=True, fast_period=12, slow_period=26, signal_period=9)
        df = compute_macd(sample_ohlcv, config)
        assert "macd_line" in df.columns
        assert "macd_signal_line" in df.columns
        assert "macd_histogram" in df.columns
        assert "macd_signal" in df.columns

    def test_histogram_is_difference(self, sample_ohlcv):
        config = MACDConfig(enabled=True, fast_period=12, slow_period=26, signal_period=9)
        df = compute_macd(sample_ohlcv, config)
        valid = df.dropna(subset=["macd_line", "macd_signal_line", "macd_histogram"])
        diff = valid["macd_line"] - valid["macd_signal_line"]
        pd.testing.assert_series_equal(
            valid["macd_histogram"].reset_index(drop=True),
            diff.reset_index(drop=True),
            check_names=False,
            atol=1e-10,
        )


class TestBollingerBands:
    def test_adds_columns(self, sample_ohlcv):
        config = BollingerConfig(enabled=True, period=20, std_dev=2.0)
        df = compute_bollinger(sample_ohlcv, config)
        assert "bb_upper" in df.columns
        assert "bb_middle" in df.columns
        assert "bb_lower" in df.columns
        assert "bb_signal" in df.columns

    def test_band_ordering(self, sample_ohlcv):
        """Upper band should always be above middle, middle above lower."""
        config = BollingerConfig(enabled=True, period=20, std_dev=2.0)
        df = compute_bollinger(sample_ohlcv, config)
        valid = df.dropna(subset=["bb_upper", "bb_middle", "bb_lower"])
        assert (valid["bb_upper"] >= valid["bb_middle"]).all()
        assert (valid["bb_middle"] >= valid["bb_lower"]).all()


class TestComputeAll:
    def test_all_indicators_added(self, sample_ohlcv, default_settings):
        df = compute_all(sample_ohlcv, default_settings)
        expected_cols = [
            "rsi", "rsi_signal",
            "sma_short", "sma_long", "sma_signal",
            "macd_line", "macd_signal_line", "macd_histogram", "macd_signal",
            "bb_upper", "bb_middle", "bb_lower", "bb_signal",
        ]
        for col in expected_cols:
            assert col in df.columns, f"Missing column: {col}"

    def test_disabled_indicators_skipped(self, sample_ohlcv, default_settings):
        from dataclasses import replace

        settings = replace(
            default_settings,
            rsi=replace(default_settings.rsi, enabled=False),
            macd=replace(default_settings.macd, enabled=False),
        )
        df = compute_all(sample_ohlcv, settings)
        assert "rsi" not in df.columns
        assert "macd_line" not in df.columns
        assert "sma_short" in df.columns
        assert "bb_upper" in df.columns
