"""Automatic trading scheduler for multi-user dashboard.

This module provides background job scheduling for automated trading.
Each user can enable/disable their own automated trading schedule.
"""

import logging
from datetime import datetime, time
from typing import Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from alpaca_trader.client import AlpacaClient
from alpaca_trader.config import (
    RSIConfig, SMAConfig, MACDConfig, BollingerConfig,
    SignalConfig, ExecutionConfig, DataConfig, ScheduleConfig, Settings
)
from alpaca_trader.data import fetch_bars
from alpaca_trader.indicators import compute_all
from alpaca_trader.models import Account, AuditLog, Settings as SettingsModel, User, Watchlist, db
from alpaca_trader.executor import OrderExecutor
from alpaca_trader.security import EncryptionManager
from alpaca_trader.signals import Action, evaluate_signals

logger = logging.getLogger("alpaca_trader")


class AutoTrader:
    """Background scheduler for automated trading."""

    def __init__(self, app, encryption_manager: EncryptionManager):
        """Initialize the auto trader with Flask app context."""
        self.app = app
        self.encryption_manager = encryption_manager
        self.scheduler = BackgroundScheduler()
        self.scheduler.start()
        logger.info("AutoTrader scheduler started")

    def start(self):
        """Start the scheduled job."""
        # Add a job that runs every 5 minutes to check all users
        self.scheduler.add_job(
            func=self._check_all_users,
            trigger=IntervalTrigger(minutes=5),
            id="auto_trader_check",
            name="Check all users for trading signals",
            replace_existing=True,
        )
        logger.info("AutoTrader job scheduled (every 5 minutes)")

    def stop(self):
        """Stop the scheduler."""
        self.scheduler.shutdown()
        logger.info("AutoTrader scheduler stopped")

    def _check_all_users(self):
        """Check all users with scheduling enabled and execute trades."""
        with self.app.app_context():
            try:
                # Find all users with scheduling enabled
                users_with_scheduling = (
                    db.session.query(User)
                    .join(SettingsModel)
                    .filter(SettingsModel.schedule_enabled == True)
                    .all()
                )

                logger.info(
                    "AutoTrader checking %d users with scheduling enabled",
                    len(users_with_scheduling)
                )

                for user in users_with_scheduling:
                    try:
                        self._process_user(user)
                    except Exception as e:
                        logger.exception("Failed to process user %s: %s", user.username, e)
                        # Log audit event for the error
                        self._log_audit(
                            user_id=user.id,
                            action="auto_trade_error",
                            details={"error": str(e)}
                        )

            except Exception as e:
                logger.exception("AutoTrader check failed: %s", e)

    def _process_user(self, user: User):
        """Process a single user's automated trading."""
        logger.info("Processing user: %s", user.username)

        # Get user's settings
        settings_db = SettingsModel.query.filter_by(user_id=user.id).first()
        if not settings_db:
            logger.warning("User %s has no settings, skipping", user.username)
            return

        # Check if it's within scheduled time (market hours only check)
        # Use UTC and compare against ET market hours (ET = UTC-5 in winter, UTC-4 in summer)
        if settings_db.schedule_market_hours_only:
            from datetime import timezone
            now_utc = datetime.now(timezone.utc)
            now_utc_time = now_utc.time().replace(tzinfo=None)

            if settings_db.execution_extended_hours:
                # Extended hours: pre-market (4 AM ET) through after-hours (8 PM ET)
                # 4:00 AM ET = 09:00 UTC, 8:00 PM ET = 01:00 UTC (crosses midnight)
                # Simplified: allow 09:00-23:59 UTC (covers 4 AM - 7 PM ET)
                session_open_utc = time(9, 0)
                session_close_utc = time(23, 59)
            else:
                # Regular market hours: 9:30 AM ET = 14:30 UTC (winter) / 13:30 UTC (summer)
                # Use conservative window 13:30-21:00 UTC to cover both EST and EDT
                session_open_utc = time(13, 30)
                session_close_utc = time(21, 0)

            if not (session_open_utc <= now_utc_time <= session_close_utc):
                logger.info("User %s: Outside session hours (UTC %s), skipping",
                            user.username, now_utc_time.strftime("%H:%M"))
                return

        # Get user's active account
        active_account = Account.query.filter_by(user_id=user.id, is_active=True).first()
        if not active_account:
            logger.warning("User %s has no active account, skipping", user.username)
            return

        # Decrypt API keys and create client
        api_key = self.encryption_manager.decrypt(active_account.api_key_encrypted)
        secret_key = self.encryption_manager.decrypt(active_account.secret_key_encrypted)
        client = AlpacaClient(api_key, secret_key, paper=active_account.is_paper)

        # Create Settings object
        settings = self._create_settings_object(settings_db)

        # Get user's watchlist
        watchlist_entries = Watchlist.query.filter_by(user_id=user.id).all()
        symbols = [entry.symbol for entry in watchlist_entries]

        if not symbols:
            logger.info("User %s has empty watchlist, skipping", user.username)
            return

        # Fetch bars and evaluate signals
        bars = fetch_bars(client, symbols, settings.data.timeframe, settings.data.lookback_days)

        # Create order executor
        executor = OrderExecutor(client, settings)

        signals_processed = 0
        trades_executed = 0

        for symbol, df in bars.items():
            try:
                # Compute indicators and evaluate signal
                df = compute_all(df, settings)
                signal = evaluate_signals(df, symbol, settings)

                logger.info(
                    "User %s, Symbol %s: Signal=%s, Strength=%.1f%%",
                    user.username,
                    symbol,
                    signal.action.value,
                    signal.strength * 100
                )

                signals_processed += 1

                # Execute trade based on signal
                if signal.action == Action.BUY:
                    result = executor.execute_signal(signal)
                    if result:
                        trades_executed += 1
                        self._log_audit(
                            user_id=user.id,
                            action="auto_trade_buy",
                            resource_type="order",
                            resource_id=None,
                            details={
                                "symbol": symbol,
                                "signal_strength": signal.strength,
                                "order_id": result.get("order_id")
                            }
                        )
                        logger.info("User %s: BUY order placed for %s - Order ID: %s",
                                    user.username, symbol, result.get("order_id"))

                elif signal.action == Action.SELL:
                    result = executor.execute_signal(signal)
                    if result:
                        trades_executed += 1
                        self._log_audit(
                            user_id=user.id,
                            action="auto_trade_sell",
                            resource_type="order",
                            resource_id=None,
                            details={
                                "symbol": symbol,
                                "signal_strength": signal.strength,
                                "order_id": result.get("order_id")
                            }
                        )
                        logger.info("User %s: SELL order placed for %s - Order ID: %s",
                                    user.username, symbol, result.get("order_id"))

            except Exception as e:
                logger.exception("Failed to process symbol %s for user %s: %s", symbol, user.username, e)

        logger.info(
            "User %s: Processed %d signals, executed %d trades",
            user.username,
            signals_processed,
            trades_executed
        )

        # Log summary audit event
        self._log_audit(
            user_id=user.id,
            action="auto_trade_cycle",
            details={
                "signals_processed": signals_processed,
                "trades_executed": trades_executed,
                "timestamp": datetime.utcnow().isoformat()
            }
        )

    def _create_settings_object(self, settings_db: SettingsModel) -> Settings:
        """Convert database settings to Settings dataclass."""
        return Settings(
            rsi=RSIConfig(
                enabled=settings_db.rsi_enabled,
                period=settings_db.rsi_period,
                overbought=settings_db.rsi_overbought,
                oversold=settings_db.rsi_oversold
            ),
            sma=SMAConfig(
                enabled=settings_db.sma_enabled,
                short_period=settings_db.sma_short_period,
                long_period=settings_db.sma_long_period
            ),
            macd=MACDConfig(
                enabled=settings_db.macd_enabled,
                fast_period=settings_db.macd_fast_period,
                slow_period=settings_db.macd_slow_period,
                signal_period=settings_db.macd_signal_period
            ),
            bollinger=BollingerConfig(
                enabled=settings_db.bollinger_enabled,
                period=settings_db.bollinger_period,
                std_dev=settings_db.bollinger_std_dev
            ),
            signal=SignalConfig(
                mode=settings_db.signal_mode,
                min_agree=settings_db.signal_min_agree
            ),
            execution=ExecutionConfig(
                order_type=settings_db.execution_order_type,
                time_in_force=settings_db.execution_time_in_force,
                position_size_pct=settings_db.execution_position_size_pct,
                max_positions=settings_db.execution_max_positions,
                allow_short=settings_db.execution_allow_short,
                extended_hours=settings_db.execution_extended_hours,
            ),
            data=DataConfig(
                timeframe=settings_db.timeframe,
                lookback_days=settings_db.lookback_days
            ),
            schedule=ScheduleConfig(
                enabled=settings_db.schedule_enabled,
                interval_minutes=settings_db.schedule_interval_minutes,
                cron=settings_db.schedule_cron,
                market_hours_only=settings_db.schedule_market_hours_only
            )
        )

    def _log_audit(self, user_id: int, action: str, resource_type: str = None,
                   resource_id: int = None, details: dict = None):
        """Log audit event."""
        try:
            import json
            audit_log = AuditLog(
                user_id=user_id,
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                details=json.dumps(details) if details else None,
                ip_address="127.0.0.1",  # Scheduler runs locally
                user_agent="AutoTrader/1.0"
            )
            db.session.add(audit_log)
            db.session.commit()
        except Exception as e:
            logger.error("Failed to log audit event: %s", e)
            db.session.rollback()
