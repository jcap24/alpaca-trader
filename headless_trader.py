"""
Headless Alpaca Trader - Automated trading bot without UI.

This is a lightweight background worker that:
- Runs 24/7 checking for trading signals
- Executes trades automatically
- No web UI, no database, no authentication
- Configuration via YAML files
- Perfect for personal use on free hosting tier
"""

import logging
import os
import signal
import sys
from datetime import datetime, time
from pathlib import Path
from typing import Optional

import yaml
from apscheduler.schedulers.blocking import BlockingScheduler
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


class HeadlessTrader:
    """Headless automated trading bot."""

    def __init__(
        self,
        config_path: str = "config/settings.yaml",
        watchlist_path: str = "config/watchlist.yaml"
    ):
        """Initialize the headless trader."""
        logger.info("=" * 80)
        logger.info("Initializing Headless Trader")
        logger.info("=" * 80)

        # Load configuration
        self.settings = load_settings(Path(config_path))
        self.watchlist = self._load_watchlist(Path(watchlist_path))

        # Check if trading is enabled
        self.trading_enabled = os.getenv("TRADING_ENABLED", "false").lower() == "true"
        logger.info(f"Trading enabled: {self.trading_enabled}")

        if not self.trading_enabled:
            logger.warning("[WARNING] TRADING IS DISABLED - Set TRADING_ENABLED=true to enable")

        # Initialize Alpaca client
        api_key = os.getenv("ALPACA_API_KEY")
        secret_key = os.getenv("ALPACA_SECRET_KEY")
        is_paper = os.getenv("ALPACA_PAPER", "true").lower() == "true"

        if not api_key or not secret_key:
            raise ValueError("ALPACA_API_KEY and ALPACA_SECRET_KEY must be set")

        self.client = AlpacaClient(api_key, secret_key, paper=is_paper)
        self.executor = OrderExecutor(self.client, self.settings)

        account_type = "PAPER" if is_paper else "LIVE"
        logger.info(f"Connected to Alpaca ({account_type} trading)")
        logger.info(f"Watchlist: {len(self.watchlist)} symbols")
        logger.info(f"Check interval: {self.settings.schedule.interval_minutes} minutes")

        # Initialize scheduler
        self.scheduler = BlockingScheduler()
        self._setup_scheduler()

        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _load_watchlist(self, path: Path) -> list[str]:
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

    def _setup_scheduler(self):
        """Setup the background scheduler."""
        interval = self.settings.schedule.interval_minutes

        self.scheduler.add_job(
            func=self._check_signals,
            trigger="interval",
            minutes=interval,
            id="check_signals",
            name="Check trading signals",
            next_run_time=datetime.now(),  # Run immediately on start
        )

        logger.info(f"Scheduler configured to run every {interval} minutes")

    def _check_signals(self):
        """Check trading signals and execute trades."""
        logger.info("-" * 80)
        logger.info(f"Checking signals at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        # Check if we should skip (market hours only)
        if self.settings.schedule.market_hours_only:
            now = datetime.now().time()
            market_open = time(9, 30)
            market_close = time(16, 0)

            if not (market_open <= now <= market_close):
                logger.info("Outside market hours, skipping check")
                return

        if not self.watchlist:
            logger.warning("Watchlist is empty, nothing to check")
            return

        try:
            # Fetch market data
            logger.info(f"Fetching data for {len(self.watchlist)} symbols...")
            bars = fetch_bars(
                self.client,
                self.watchlist,
                self.settings.data.timeframe,
                self.settings.data.lookback_days
            )

            signals_checked = 0
            buy_signals = 0
            sell_signals = 0
            trades_executed = 0

            # Evaluate each symbol
            for symbol, df in bars.items():
                try:
                    # Compute indicators
                    df = compute_all(df, self.settings)

                    # Evaluate signal
                    signal = evaluate_signals(df, symbol, self.settings)
                    signals_checked += 1

                    logger.info(
                        f"{symbol}: {signal.action.value.upper()} "
                        f"(strength: {signal.strength*100:.1f}%) "
                        f"- {signal.details}"
                    )

                    if signal.action == Action.BUY:
                        buy_signals += 1
                        if self.trading_enabled:
                            result = self.executor.execute_signal(signal)
                            if result:
                                trades_executed += 1
                                logger.info(f"[ORDER] BUY order placed for {symbol} - Order ID: {result.get('order_id')}")
                        else:
                            logger.info(f"[SIGNAL] BUY signal for {symbol} (trading disabled)")

                    elif signal.action == Action.SELL:
                        sell_signals += 1
                        if self.trading_enabled:
                            result = self.executor.execute_signal(signal)
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

    def _signal_handler(self, signum, frame):
        """Handle shutdown signals gracefully."""
        logger.info(f"Received signal {signum}, shutting down gracefully...")
        self.stop()
        sys.exit(0)

    def start(self):
        """Start the trader."""
        logger.info("=" * 80)
        logger.info("Headless Trader Started")
        logger.info("=" * 80)
        logger.info("Press Ctrl+C to stop")
        logger.info("")

        try:
            self.scheduler.start()
        except (KeyboardInterrupt, SystemExit):
            logger.info("Shutdown requested")
            self.stop()

    def stop(self):
        """Stop the trader."""
        logger.info("Stopping scheduler...")
        if self.scheduler.running:
            self.scheduler.shutdown()
        logger.info("=" * 80)
        logger.info("Headless Trader Stopped")
        logger.info("=" * 80)


def main():
    """Entry point for headless trader."""
    trader = HeadlessTrader()
    trader.start()


if __name__ == "__main__":
    main()
