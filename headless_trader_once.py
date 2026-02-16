"""
Headless Trader - Single Run Mode

Runs once, checks signals, executes trades, then exits.
Perfect for cron jobs, GitHub Actions, or scheduled tasks.
"""

import logging
import os
import sys
from datetime import datetime, time
from pathlib import Path

import yaml
from dotenv import load_dotenv

from alpaca_trader.client import AlpacaClient
from alpaca_trader.config import Settings, load_settings
from alpaca_trader.data import fetch_bars
from alpaca_trader.executor import OrderExecutor
from alpaca_trader.indicators import compute_all
from alpaca_trader.signals import Action, evaluate_signals

# Load environment variables
load_dotenv()

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("headless_trader.log")
    ]
)
logger = logging.getLogger("headless_trader")


def load_watchlist(path: Path) -> list[str]:
    """Load watchlist from YAML file."""
    try:
        with open(path, "r") as f:
            data = yaml.safe_load(f)
            symbols = [entry["symbol"] for entry in data.get("watchlist", [])]
            logger.info(f"Loaded {len(symbols)} symbols from watchlist")
            return symbols
    except Exception as e:
        logger.error(f"Failed to load watchlist: {e}")
        return []


def check_signals_once():
    """Check signals once and exit."""
    logger.info("=" * 80)
    logger.info("Headless Trader - Single Run Mode")
    logger.info("=" * 80)

    # Load configuration
    settings = load_settings(Path("config/settings.yaml"))
    watchlist = load_watchlist(Path("config/watchlist.yaml"))

    # Check if trading is enabled
    trading_enabled = os.getenv("TRADING_ENABLED", "false").lower() == "true"
    logger.info(f"Trading enabled: {trading_enabled}")

    if not trading_enabled:
        logger.warning("[WARNING] TRADING IS DISABLED - Set TRADING_ENABLED=true to enable")

    # Initialize Alpaca client
    api_key = os.getenv("ALPACA_API_KEY")
    secret_key = os.getenv("ALPACA_SECRET_KEY")
    is_paper = os.getenv("ALPACA_PAPER", "true").lower() == "true"

    if not api_key or not secret_key:
        logger.error("ALPACA_API_KEY and ALPACA_SECRET_KEY must be set")
        sys.exit(1)

    client = AlpacaClient(api_key, secret_key, paper=is_paper)
    executor = OrderExecutor(client, settings)

    account_type = "PAPER" if is_paper else "LIVE"
    logger.info(f"Connected to Alpaca ({account_type} trading)")
    logger.info(f"Watchlist: {len(watchlist)} symbols")

    # Check if we should skip (market hours only)
    if settings.schedule.market_hours_only:
        now = datetime.now().time()
        market_open = time(9, 30)
        market_close = time(16, 0)

        if not (market_open <= now <= market_close):
            logger.info("Outside market hours, exiting")
            return

    if not watchlist:
        logger.warning("Watchlist is empty, nothing to check")
        return

    logger.info("-" * 80)
    logger.info(f"Checking signals at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    try:
        # Fetch market data
        logger.info(f"Fetching data for {len(watchlist)} symbols...")
        bars = fetch_bars(
            client,
            watchlist,
            settings.data.timeframe,
            settings.data.lookback_days
        )

        signals_checked = 0
        buy_signals = 0
        sell_signals = 0
        trades_executed = 0

        # Evaluate each symbol
        for symbol, df in bars.items():
            try:
                # Compute indicators
                df = compute_all(df, settings)

                # Evaluate signal
                signal = evaluate_signals(df, symbol, settings)
                signals_checked += 1

                logger.info(
                    f"{symbol}: {signal.action.value.upper()} "
                    f"(strength: {signal.strength*100:.1f}%) "
                    f"- {signal.details}"
                )

                if signal.action == Action.BUY:
                    buy_signals += 1
                    if trading_enabled:
                        result = executor.execute_signal(signal)
                        if result:
                            trades_executed += 1
                            logger.info(f"[ORDER] BUY order placed for {symbol} - Order ID: {result.get('order_id')}")
                    else:
                        logger.info(f"[SIGNAL] BUY signal for {symbol} (trading disabled)")

                elif signal.action == Action.SELL:
                    sell_signals += 1
                    if trading_enabled:
                        result = executor.execute_signal(signal)
                        if result:
                            trades_executed += 1
                            logger.info(f"[ORDER] SELL order placed for {symbol} - Order ID: {result.get('order_id')}")
                    else:
                        logger.info(f"[SIGNAL] SELL signal for {symbol} (trading disabled)")

            except Exception as e:
                logger.exception(f"Error processing {symbol}: {e}")

        # Summary
        logger.info(
            f"Summary: {signals_checked} signals checked, "
            f"{buy_signals} BUY, {sell_signals} SELL, "
            f"{trades_executed} trades executed"
        )

    except Exception as e:
        logger.exception(f"Error in signal check: {e}")
        sys.exit(1)

    logger.info("=" * 80)
    logger.info("Run completed successfully")
    logger.info("=" * 80)


if __name__ == "__main__":
    check_signals_once()
