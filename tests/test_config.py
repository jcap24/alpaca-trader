import tempfile
from pathlib import Path

import pytest
import yaml

from alpaca_trader.config import load_settings, load_watchlist


class TestLoadSettings:
    def test_loads_valid_config(self, tmp_path):
        config = {
            "indicators": {
                "rsi": {"enabled": True, "period": 14, "overbought": 70, "oversold": 30},
                "sma_crossover": {"enabled": True, "short_period": 20, "long_period": 50},
                "macd": {"enabled": True, "fast_period": 12, "slow_period": 26, "signal_period": 9},
                "bollinger_bands": {"enabled": False, "period": 20, "std_dev": 2.0},
            },
            "signal": {"mode": "majority", "min_agree": 2},
            "execution": {
                "order_type": "market",
                "time_in_force": "day",
                "position_size_pct": 5.0,
                "max_positions": 10,
                "allow_short": False,
            },
            "data": {"timeframe": "1Day", "lookback_days": 100},
            "schedule": {
                "enabled": False,
                "interval_minutes": 60,
                "cron": None,
                "market_hours_only": True,
            },
        }
        config_file = tmp_path / "settings.yaml"
        config_file.write_text(yaml.dump(config))

        settings = load_settings(config_file)
        assert settings.rsi.enabled is True
        assert settings.rsi.period == 14
        assert settings.bollinger.enabled is False
        assert settings.signal.mode == "majority"
        assert settings.execution.position_size_pct == 5.0
        assert settings.data.timeframe == "1Day"

    def test_missing_key_raises(self, tmp_path):
        config = {"indicators": {}}  # Missing required keys
        config_file = tmp_path / "settings.yaml"
        config_file.write_text(yaml.dump(config))

        with pytest.raises(KeyError):
            load_settings(config_file)


class TestLoadWatchlist:
    def test_loads_symbols(self, tmp_path):
        watchlist = {
            "watchlist": [
                {"symbol": "AAPL", "name": "Apple"},
                {"symbol": "MSFT", "name": "Microsoft"},
            ]
        }
        wl_file = tmp_path / "watchlist.yaml"
        wl_file.write_text(yaml.dump(watchlist))

        symbols = load_watchlist(wl_file)
        assert symbols == ["AAPL", "MSFT"]

    def test_empty_watchlist(self, tmp_path):
        watchlist = {"watchlist": []}
        wl_file = tmp_path / "watchlist.yaml"
        wl_file.write_text(yaml.dump(watchlist))

        symbols = load_watchlist(wl_file)
        assert symbols == []
