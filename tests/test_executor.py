from dataclasses import replace
from unittest.mock import MagicMock, patch

import pytest

from alpaca_trader.executor import OrderExecutor
from alpaca_trader.signals import Action, Signal


def _make_mock_client(equity=100000, positions=None, existing_position=None):
    """Create a mock AlpacaClient."""
    client = MagicMock()

    account = MagicMock()
    account.equity = str(equity)
    client.get_account.return_value = account

    client.get_positions.return_value = positions or []
    client.get_position.return_value = existing_position

    order = MagicMock()
    order.id = "test-order-123"
    order.status = "accepted"
    client.submit_order.return_value = order

    return client


class TestOrderExecutor:
    def test_hold_does_nothing(self, default_settings):
        client = _make_mock_client()
        executor = OrderExecutor(client, default_settings)
        signal = Signal(symbol="AAPL", action=Action.HOLD, strength=0.0, details={})
        result = executor.execute_signal(signal)
        assert result is None
        client.submit_order.assert_not_called()

    def test_buy_submits_order(self, default_settings):
        client = _make_mock_client()
        executor = OrderExecutor(client, default_settings)
        signal = Signal(symbol="AAPL", action=Action.BUY, strength=0.75, details={})
        result = executor.execute_signal(signal)
        assert result is not None
        assert result["order_id"] == "test-order-123"
        client.submit_order.assert_called_once()

    def test_buy_notional_is_correct(self, default_settings):
        """5% of $100,000 = $5,000."""
        client = _make_mock_client(equity=100000)
        executor = OrderExecutor(client, default_settings)
        signal = Signal(symbol="AAPL", action=Action.BUY, strength=0.5, details={})
        executor.execute_signal(signal)
        order_request = client.submit_order.call_args[0][0]
        assert float(order_request.notional) == 5000.0

    def test_buy_blocked_at_max_positions(self, default_settings):
        positions = [MagicMock() for _ in range(10)]
        client = _make_mock_client(positions=positions, existing_position=None)
        executor = OrderExecutor(client, default_settings)
        signal = Signal(symbol="NEW", action=Action.BUY, strength=0.5, details={})
        result = executor.execute_signal(signal)
        assert result is None
        client.submit_order.assert_not_called()

    def test_buy_blocked_already_holding(self, default_settings):
        existing = MagicMock()
        existing.qty = "10"
        client = _make_mock_client(existing_position=existing)
        executor = OrderExecutor(client, default_settings)
        signal = Signal(symbol="AAPL", action=Action.BUY, strength=0.5, details={})
        result = executor.execute_signal(signal)
        assert result is None

    def test_sell_full_position(self, default_settings):
        existing = MagicMock()
        existing.qty = "15"
        client = _make_mock_client(existing_position=existing)
        executor = OrderExecutor(client, default_settings)
        signal = Signal(symbol="AAPL", action=Action.SELL, strength=0.5, details={})
        result = executor.execute_signal(signal)
        assert result is not None
        order_request = client.submit_order.call_args[0][0]
        assert float(order_request.qty) == 15.0

    def test_sell_no_position_no_short(self, default_settings):
        """With allow_short=False, can't sell what we don't own."""
        client = _make_mock_client(existing_position=None)
        executor = OrderExecutor(client, default_settings)
        signal = Signal(symbol="AAPL", action=Action.SELL, strength=0.5, details={})
        result = executor.execute_signal(signal)
        assert result is None

    def test_sell_no_position_short_allowed(self, default_settings):
        settings = replace(
            default_settings,
            execution=replace(default_settings.execution, allow_short=True),
        )
        client = _make_mock_client(existing_position=None)
        executor = OrderExecutor(client, settings)
        signal = Signal(symbol="AAPL", action=Action.SELL, strength=0.5, details={})
        result = executor.execute_signal(signal)
        assert result is not None

    def test_dry_run_does_not_submit(self, default_settings):
        client = _make_mock_client()
        executor = OrderExecutor(client, default_settings)
        signal = Signal(symbol="AAPL", action=Action.BUY, strength=0.5, details={})
        result = executor.execute_signal(signal, dry_run=True)
        assert result is not None
        assert result["dry_run"] is True
        client.submit_order.assert_not_called()
