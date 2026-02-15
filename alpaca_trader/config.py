from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import yaml
from dotenv import load_dotenv
import os


@dataclass
class RSIConfig:
    enabled: bool
    period: int
    overbought: float
    oversold: float


@dataclass
class SMAConfig:
    enabled: bool
    short_period: int
    long_period: int


@dataclass
class MACDConfig:
    enabled: bool
    fast_period: int
    slow_period: int
    signal_period: int


@dataclass
class BollingerConfig:
    enabled: bool
    period: int
    std_dev: float


@dataclass
class SignalConfig:
    mode: str  # "majority", "unanimous", "any"
    min_agree: int


@dataclass
class ExecutionConfig:
    order_type: str
    time_in_force: str
    position_size_pct: float
    max_positions: int
    allow_short: bool


@dataclass
class DataConfig:
    timeframe: str
    lookback_days: int


@dataclass
class ScheduleConfig:
    enabled: bool
    interval_minutes: int
    cron: Optional[str]
    market_hours_only: bool


@dataclass
class Settings:
    rsi: RSIConfig
    sma: SMAConfig
    macd: MACDConfig
    bollinger: BollingerConfig
    signal: SignalConfig
    execution: ExecutionConfig
    data: DataConfig
    schedule: ScheduleConfig


def load_settings(config_path: Path) -> Settings:
    """Load and validate settings from a YAML file."""
    with open(config_path, "r") as f:
        raw = yaml.safe_load(f)

    ind = raw["indicators"]

    rsi = RSIConfig(
        enabled=ind["rsi"]["enabled"],
        period=ind["rsi"]["period"],
        overbought=ind["rsi"]["overbought"],
        oversold=ind["rsi"]["oversold"],
    )
    sma = SMAConfig(
        enabled=ind["sma_crossover"]["enabled"],
        short_period=ind["sma_crossover"]["short_period"],
        long_period=ind["sma_crossover"]["long_period"],
    )
    macd = MACDConfig(
        enabled=ind["macd"]["enabled"],
        fast_period=ind["macd"]["fast_period"],
        slow_period=ind["macd"]["slow_period"],
        signal_period=ind["macd"]["signal_period"],
    )
    bollinger = BollingerConfig(
        enabled=ind["bollinger_bands"]["enabled"],
        period=ind["bollinger_bands"]["period"],
        std_dev=ind["bollinger_bands"]["std_dev"],
    )

    sig = raw["signal"]
    signal = SignalConfig(mode=sig["mode"], min_agree=sig["min_agree"])

    exe = raw["execution"]
    execution = ExecutionConfig(
        order_type=exe["order_type"],
        time_in_force=exe["time_in_force"],
        position_size_pct=exe["position_size_pct"],
        max_positions=exe["max_positions"],
        allow_short=exe["allow_short"],
    )

    d = raw["data"]
    data = DataConfig(timeframe=d["timeframe"], lookback_days=d["lookback_days"])

    sch = raw["schedule"]
    schedule = ScheduleConfig(
        enabled=sch["enabled"],
        interval_minutes=sch["interval_minutes"],
        cron=sch.get("cron"),
        market_hours_only=sch["market_hours_only"],
    )

    return Settings(
        rsi=rsi,
        sma=sma,
        macd=macd,
        bollinger=bollinger,
        signal=signal,
        execution=execution,
        data=data,
        schedule=schedule,
    )


def load_watchlist(watchlist_path: Path) -> list[str]:
    """Load stock symbols from the watchlist YAML file."""
    with open(watchlist_path, "r") as f:
        raw = yaml.safe_load(f)

    return [entry["symbol"] for entry in raw["watchlist"]]


def load_api_keys() -> tuple[str, str]:
    """Load Alpaca API keys from .env file."""
    load_dotenv()

    api_key = os.getenv("ALPACA_API_KEY")
    secret_key = os.getenv("ALPACA_SECRET_KEY")

    if not api_key or not secret_key:
        raise ValueError(
            "ALPACA_API_KEY and ALPACA_SECRET_KEY must be set in .env file. "
            "Copy .env.example to .env and fill in your keys."
        )

    return api_key, secret_key
