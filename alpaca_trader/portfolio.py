import logging

from alpaca_trader.client import AlpacaClient

logger = logging.getLogger("alpaca_trader")


class PortfolioManager:
    """Queries account info, positions, and market status."""

    def __init__(self, client: AlpacaClient):
        self.client = client

    def get_summary(self) -> dict:
        """Return account summary: equity, cash, buying power."""
        account = self.client.get_account()

        def safe_float(val, fallback=0.0):
            try:
                return float(val) if val is not None else fallback
            except (TypeError, ValueError):
                return fallback

        equity = safe_float(account.equity)
        return {
            "equity": equity,
            "cash": safe_float(account.cash),
            "buying_power": safe_float(account.buying_power),
            "portfolio_value": safe_float(account.portfolio_value, equity),
        }

    def get_positions_summary(self) -> list[dict]:
        """Return a list of open positions with key metrics."""
        positions = self.client.get_positions()
        return [
            {
                "symbol": p.symbol,
                "qty": float(p.qty),
                "market_value": float(p.market_value),
                "avg_entry": float(p.avg_entry_price),
                "unrealized_pl": float(p.unrealized_pl),
                "unrealized_plpc": float(p.unrealized_plpc),
            }
            for p in positions
        ]

    def is_market_open(self) -> bool:
        """Check if the market is currently open."""
        clock = self.client.trading.get_clock()
        return clock.is_open
