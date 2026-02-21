import logging
from typing import Optional

from alpaca.trading.requests import LimitOrderRequest, MarketOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce

from alpaca_trader.client import AlpacaClient
from alpaca_trader.config import Settings
from alpaca_trader.signals import Action, Signal

logger = logging.getLogger("alpaca_trader")

TIME_IN_FORCE_MAP = {
    "day": TimeInForce.DAY,
    "gtc": TimeInForce.GTC,
    "ioc": TimeInForce.IOC,
}


class OrderExecutor:
    """Translates signals into Alpaca orders with safety guards."""

    def __init__(self, client: AlpacaClient, settings: Settings):
        self.client = client
        self.settings = settings

    def execute_signal(
        self, signal: Signal, dry_run: bool = False
    ) -> Optional[dict]:
        """
        Given a Signal, check guards and submit an order if appropriate.
        Returns order details dict, or None if no action taken.
        """
        if signal.action == Action.HOLD:
            return None

        account = self.client.get_account()
        equity = float(account.equity)
        positions = self.client.get_positions()
        existing_position = self.client.get_position(signal.symbol)

        # --- Guard: max positions ---
        if signal.action == Action.BUY and existing_position is None:
            if len(positions) >= self.settings.execution.max_positions:
                logger.info(
                    "Skipping BUY %s: max positions (%d) reached",
                    signal.symbol,
                    self.settings.execution.max_positions,
                )
                return None

        # --- Guard: already holding ---
        if signal.action == Action.BUY and existing_position is not None:
            logger.info("Skipping BUY %s: already in position", signal.symbol)
            return None

        # --- Guard: nothing to sell ---
        if signal.action == Action.SELL and existing_position is None:
            if not self.settings.execution.allow_short:
                logger.info(
                    "Skipping SELL %s: no position and shorting disabled",
                    signal.symbol,
                )
                return None

        # --- Calculate order parameters ---
        tif = TIME_IN_FORCE_MAP[self.settings.execution.time_in_force]
        extended_hours = self.settings.execution.extended_hours

        # Alpaca requires limit orders (not market) for extended-hours sessions
        if extended_hours and not signal.price:
            logger.warning(
                "Skipping %s %s: extended_hours enabled but no price available for limit order",
                signal.action.value, signal.symbol,
            )
            return None

        if signal.action == Action.BUY:
            notional = round(
                equity * (self.settings.execution.position_size_pct / 100.0), 2
            )
            if extended_hours:
                limit_price = round(float(signal.price), 2)
                qty = round(notional / limit_price, 4)
                order_request = LimitOrderRequest(
                    symbol=signal.symbol,
                    qty=qty,
                    side=OrderSide.BUY,
                    time_in_force=TimeInForce.DAY,  # required for extended hours
                    limit_price=limit_price,
                    extended_hours=True,
                )
                order_desc = f"BUY {signal.symbol} qty={qty} @ limit ${limit_price} (extended hours)"
            else:
                order_request = MarketOrderRequest(
                    symbol=signal.symbol,
                    notional=notional,
                    side=OrderSide.BUY,
                    time_in_force=tif,
                )
                order_desc = f"BUY {signal.symbol} notional=${notional}"

        elif signal.action == Action.SELL and existing_position is not None:
            qty = abs(float(existing_position.qty))
            if extended_hours:
                limit_price = round(float(signal.price), 2)
                order_request = LimitOrderRequest(
                    symbol=signal.symbol,
                    qty=qty,
                    side=OrderSide.SELL,
                    time_in_force=TimeInForce.DAY,
                    limit_price=limit_price,
                    extended_hours=True,
                )
                order_desc = f"SELL {signal.symbol} qty={qty} @ limit ${limit_price} (extended hours)"
            else:
                order_request = MarketOrderRequest(
                    symbol=signal.symbol,
                    qty=qty,
                    side=OrderSide.SELL,
                    time_in_force=tif,
                )
                order_desc = f"SELL {signal.symbol} qty={qty}"

        else:
            # Short sell (allow_short is true, no existing position)
            notional = round(
                equity * (self.settings.execution.position_size_pct / 100.0), 2
            )
            if extended_hours:
                limit_price = round(float(signal.price), 2)
                qty = round(notional / limit_price, 4)
                order_request = LimitOrderRequest(
                    symbol=signal.symbol,
                    qty=qty,
                    side=OrderSide.SELL,
                    time_in_force=TimeInForce.DAY,
                    limit_price=limit_price,
                    extended_hours=True,
                )
                order_desc = f"SHORT SELL {signal.symbol} qty={qty} @ limit ${limit_price} (extended hours)"
            else:
                order_request = MarketOrderRequest(
                    symbol=signal.symbol,
                    notional=notional,
                    side=OrderSide.SELL,
                    time_in_force=tif,
                )
                order_desc = f"SHORT SELL {signal.symbol} notional=${notional}"

        # --- Dry run ---
        if dry_run:
            logger.info("[DRY RUN] Would submit: %s", order_desc)
            return {
                "dry_run": True,
                "symbol": signal.symbol,
                "description": order_desc,
            }

        # --- Submit order ---
        order = self.client.submit_order(order_request)
        logger.info(
            "Order submitted: %s | ID=%s | status=%s",
            order_desc,
            order.id,
            order.status,
        )
        return {
            "order_id": str(order.id),
            "symbol": signal.symbol,
            "side": order_request.side.value,
            "status": str(order.status),
        }
