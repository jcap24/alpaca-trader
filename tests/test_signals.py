import pandas as pd
import numpy as np
from dataclasses import replace

from alpaca_trader.signals import Action, evaluate_signals


class TestSignalAggregation:
    def _make_df(self, rsi_sig=None, sma_sig=None, macd_sig=None, bb_sig=None):
        """Helper: create a 1-row DataFrame with indicator signal columns."""
        return pd.DataFrame(
            {
                "close": [150.0],
                "rsi_signal": [rsi_sig],
                "sma_signal": [sma_sig],
                "macd_signal": [macd_sig],
                "bb_signal": [bb_sig],
            }
        )

    def test_majority_buy(self, default_settings):
        """3 of 4 indicators say buy -> BUY (min_agree=2)."""
        df = self._make_df(rsi_sig="buy", sma_sig="buy", macd_sig="buy", bb_sig=None)
        signal = evaluate_signals(df, "AAPL", default_settings)
        assert signal.action == Action.BUY
        assert signal.strength == 0.75

    def test_majority_sell(self, default_settings):
        """2 of 4 indicators say sell -> SELL (min_agree=2)."""
        df = self._make_df(rsi_sig="sell", sma_sig=None, macd_sig="sell", bb_sig=None)
        signal = evaluate_signals(df, "AAPL", default_settings)
        assert signal.action == Action.SELL
        assert signal.strength == 0.5

    def test_majority_hold_not_enough(self, default_settings):
        """Only 1 indicator says buy, min_agree=2 -> HOLD."""
        df = self._make_df(rsi_sig="buy", sma_sig=None, macd_sig=None, bb_sig=None)
        signal = evaluate_signals(df, "AAPL", default_settings)
        assert signal.action == Action.HOLD

    def test_majority_conflict(self, default_settings):
        """2 buy, 2 sell -> HOLD (tie, neither side wins)."""
        df = self._make_df(rsi_sig="buy", sma_sig="buy", macd_sig="sell", bb_sig="sell")
        signal = evaluate_signals(df, "AAPL", default_settings)
        assert signal.action == Action.HOLD

    def test_unanimous_buy(self, default_settings):
        settings = replace(default_settings, signal=replace(default_settings.signal, mode="unanimous"))
        df = self._make_df(rsi_sig="buy", sma_sig="buy", macd_sig="buy", bb_sig="buy")
        signal = evaluate_signals(df, "AAPL", settings)
        assert signal.action == Action.BUY
        assert signal.strength == 1.0

    def test_unanimous_hold_partial(self, default_settings):
        """3 of 4 say buy in unanimous mode -> HOLD."""
        settings = replace(default_settings, signal=replace(default_settings.signal, mode="unanimous"))
        df = self._make_df(rsi_sig="buy", sma_sig="buy", macd_sig="buy", bb_sig=None)
        signal = evaluate_signals(df, "AAPL", settings)
        assert signal.action == Action.HOLD

    def test_any_buy(self, default_settings):
        settings = replace(default_settings, signal=replace(default_settings.signal, mode="any"))
        df = self._make_df(rsi_sig="buy", sma_sig=None, macd_sig=None, bb_sig=None)
        signal = evaluate_signals(df, "AAPL", settings)
        assert signal.action == Action.BUY

    def test_any_conflict_hold(self, default_settings):
        """In 'any' mode, conflicting signals -> HOLD."""
        settings = replace(default_settings, signal=replace(default_settings.signal, mode="any"))
        df = self._make_df(rsi_sig="buy", sma_sig=None, macd_sig="sell", bb_sig=None)
        signal = evaluate_signals(df, "AAPL", settings)
        assert signal.action == Action.HOLD

    def test_empty_dataframe(self, default_settings):
        df = pd.DataFrame()
        signal = evaluate_signals(df, "AAPL", default_settings)
        assert signal.action == Action.HOLD
        assert signal.strength == 0.0

    def test_all_none_signals(self, default_settings):
        df = self._make_df(rsi_sig=None, sma_sig=None, macd_sig=None, bb_sig=None)
        signal = evaluate_signals(df, "AAPL", default_settings)
        assert signal.action == Action.HOLD

    def test_signal_details_populated(self, default_settings):
        df = self._make_df(rsi_sig="buy", sma_sig=None, macd_sig="sell", bb_sig=None)
        signal = evaluate_signals(df, "AAPL", default_settings)
        assert "rsi_signal" in signal.details
        assert "sma_signal" in signal.details
        assert signal.details["rsi_signal"] == "buy"
        assert signal.details["macd_signal"] == "sell"
