import logging

from alpaca.trading.client import TradingClient
from alpaca.data.historical import StockHistoricalDataClient

logger = logging.getLogger("alpaca_trader")


class AlpacaClient:
    """Thin wrapper around Alpaca's trading and data clients."""

    def __init__(self, api_key: str, secret_key: str, paper: bool = True):
        self.trading = TradingClient(api_key, secret_key, paper=paper)
        self.data = StockHistoricalDataClient(api_key, secret_key)
        logger.info("Alpaca client initialized (paper=%s)", paper)

    def get_account(self):
        """Return account info (equity, buying power, etc.)."""
        return self.trading.get_account()

    def get_positions(self):
        """Return all open positions."""
        return self.trading.get_all_positions()

    def get_position(self, symbol: str):
        """Return position for a specific symbol, or None if not held."""
        try:
            return self.trading.get_open_position(symbol)
        except Exception:
            return None

    def submit_order(self, order_request):
        """Submit an order and return the Order object."""
        return self.trading.submit_order(order_data=order_request)

    def get_orders(self, filter=None):
        """Return orders with optional filter."""
        return self.trading.get_orders(filter=filter)

    def get_portfolio_history(self, filter=None):
        """Return portfolio equity history."""
        return self.trading.get_portfolio_history(history_filter=filter)

    def get_asset(self, symbol: str):
        """Get asset information for a symbol. Returns None if not found."""
        try:
            return self.trading.get_asset(symbol)
        except Exception as e:
            logger.debug("Asset lookup failed for %s: %s", symbol, e)
            return None
