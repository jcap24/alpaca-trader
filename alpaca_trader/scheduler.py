import logging

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from alpaca_trader.config import Settings

logger = logging.getLogger("alpaca_trader")


class TradingScheduler:
    """Runs a trading job on a configurable schedule."""

    def __init__(self, run_fn: callable, settings: Settings, blocking: bool = True):
        if blocking:
            self.scheduler = BlockingScheduler()
        else:
            self.scheduler = BackgroundScheduler()
        self.run_fn = run_fn
        self.settings = settings
        self._blocking = blocking

    def start(self):
        """Start the scheduler based on config (interval or cron)."""
        cron_expr = self.settings.schedule.cron

        if cron_expr:
            parts = cron_expr.split()
            trigger = CronTrigger(
                minute=parts[0],
                hour=parts[1],
                day=parts[2],
                month=parts[3],
                day_of_week=parts[4],
                timezone="US/Eastern",
            )
            logger.info("Scheduler starting with cron: %s", cron_expr)
        else:
            trigger = IntervalTrigger(
                minutes=self.settings.schedule.interval_minutes,
            )
            logger.info(
                "Scheduler starting with interval: every %d minutes",
                self.settings.schedule.interval_minutes,
            )

        self.scheduler.add_job(
            self.run_fn,
            trigger,
            id="trading_scan",
            misfire_grace_time=60,
        )

        # Run once immediately on startup
        logger.info("Running initial scan...")
        self.run_fn()

        if self._blocking:
            logger.info("Scheduler running. Press Ctrl+C to stop.")
            try:
                self.scheduler.start()
            except (KeyboardInterrupt, SystemExit):
                self.scheduler.shutdown()
                logger.info("Scheduler stopped.")
        else:
            logger.info("Scheduler running in background.")
            self.scheduler.start()

    def stop(self):
        """Shut down the scheduler gracefully."""
        if self.scheduler.running:
            self.scheduler.shutdown()
            logger.info("Scheduler stopped.")
