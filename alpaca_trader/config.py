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
    extended_hours: bool = False


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
    """
    Load Alpaca API keys from .env file (legacy) or accounts.yaml (new).
    Tries accounts.yaml first, falls back to .env if not found.
    """
    # Try loading from accounts.yaml first
    accounts_path = Path("config/accounts.yaml")
    if accounts_path.exists():
        try:
            accounts = load_accounts(accounts_path)
            active_account = get_active_account(accounts)
            if active_account:
                return active_account["api_key"], active_account["secret_key"]
        except Exception:
            pass  # Fall back to .env

    # Fall back to .env (legacy support)
    load_dotenv()

    api_key = os.getenv("ALPACA_API_KEY")
    secret_key = os.getenv("ALPACA_SECRET_KEY")

    if not api_key or not secret_key:
        raise ValueError(
            "No API keys found. Please configure accounts in the dashboard or "
            "set ALPACA_API_KEY and ALPACA_SECRET_KEY in .env file."
        )

    return api_key, secret_key


def load_accounts(accounts_path: Path) -> list[dict]:
    """Load trading accounts from accounts.yaml."""
    if not accounts_path.exists():
        return []

    with open(accounts_path, "r") as f:
        raw = yaml.safe_load(f)

    return raw.get("accounts", []) if raw else []


def save_accounts(accounts_path: Path, accounts: list[dict]) -> None:
    """Save trading accounts to accounts.yaml."""
    accounts_data = {"accounts": accounts}
    with open(accounts_path, "w") as f:
        yaml.dump(accounts_data, f, default_flow_style=False)


def get_active_account(accounts: list[dict]) -> Optional[dict]:
    """Get the currently active account."""
    # Return the first active account, or the first account if none are marked active
    for account in accounts:
        if account.get("active", False):
            return account

    # No active account marked, use the first one
    return accounts[0] if accounts else None


def set_active_account(accounts_path: Path, account_name: str) -> bool:
    """Set an account as active by name."""
    accounts = load_accounts(accounts_path)

    found = False
    for account in accounts:
        if account["name"] == account_name:
            account["active"] = True
            found = True
        else:
            account["active"] = False

    if found:
        save_accounts(accounts_path, accounts)

    return found


def add_account(accounts_path: Path, name: str, api_key: str, secret_key: str, is_paper: bool = True) -> None:
    """Add a new trading account."""
    accounts = load_accounts(accounts_path)

    # Check for duplicate names
    if any(acc["name"] == name for acc in accounts):
        raise ValueError(f"Account '{name}' already exists")

    # If this is the first account, make it active
    is_active = len(accounts) == 0

    new_account = {
        "name": name,
        "api_key": api_key,
        "secret_key": secret_key,
        "paper": is_paper,
        "active": is_active
    }

    accounts.append(new_account)
    save_accounts(accounts_path, accounts)


def update_account(accounts_path: Path, name: str, api_key: str, secret_key: str, is_paper: bool) -> bool:
    """Update an existing account."""
    accounts = load_accounts(accounts_path)

    found = False
    for account in accounts:
        if account["name"] == name:
            account["api_key"] = api_key
            account["secret_key"] = secret_key
            account["paper"] = is_paper
            found = True
            break

    if found:
        save_accounts(accounts_path, accounts)

    return found


def delete_account(accounts_path: Path, name: str) -> bool:
    """Delete an account by name."""
    accounts = load_accounts(accounts_path)
    original_count = len(accounts)

    accounts = [acc for acc in accounts if acc["name"] != name]

    if len(accounts) < original_count:
        # If we deleted the active account and there are remaining accounts,
        # make the first one active
        if accounts and not any(acc.get("active", False) for acc in accounts):
            accounts[0]["active"] = True

        save_accounts(accounts_path, accounts)
        return True

    return False
