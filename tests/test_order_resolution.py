import pytest

from app.trading.orders import OrderManager


class SubmittedThenFilledExchange:
    def __init__(self):
        self.orderbooks = {}
        self.status_calls = 0
        self.cancel_calls = 0

    async def get_order_status(self, symbol, order_id=None, client_order_id=None):
        self.status_calls += 1
        return {
            "order_id": order_id,
            "client_order_id": client_order_id,
            "status": "FILLED",
            "filled_amount": 1.0,
            "remaining_amount": 0.0,
            "avg_price": 100.0,
        }

    async def cancel_order(self, symbol, order_id=None, client_order_id=None):
        self.cancel_calls += 1
        return {"status": "CANCELED"}


class AlwaysSubmittedExchange:
    def __init__(self):
        self.cancel_calls = 0

    async def get_order_status(self, symbol, order_id=None, client_order_id=None):
        return {
            "order_id": order_id,
            "client_order_id": client_order_id,
            "status": "SUBMITTED",
            "filled_amount": 0.0,
            "remaining_amount": 1.0,
        }

    async def cancel_order(self, symbol, order_id=None, client_order_id=None):
        self.cancel_calls += 1
        return {"status": "CANCELED"}


@pytest.mark.asyncio
async def test_submitted_order_is_polled_before_trade_continues():
    exchange = SubmittedThenFilledExchange()
    manager = OrderManager({"test": exchange})
    result = await manager.resolve_order(
        "test",
        "BTCUSDT",
        {"order_id": "o-1", "client_order_id": "c-1", "status": "SUBMITTED", "filled_amount": 0.0},
        timeout_seconds=0.2,
    )

    assert result["status"] == "FILLED"
    assert result["filled_amount"] == 1.0
    assert exchange.status_calls >= 1
    assert exchange.cancel_calls == 0


@pytest.mark.asyncio
async def test_unresolved_order_triggers_cancel_and_remains_unknown_if_unconfirmed():
    exchange = AlwaysSubmittedExchange()
    manager = OrderManager({"test": exchange})
    result = await manager.resolve_order(
        "test",
        "BTCUSDT",
        {"order_id": "o-2", "client_order_id": "c-2", "status": "SUBMITTED", "filled_amount": 0.0},
        timeout_seconds=0.01,
    )

    assert exchange.cancel_calls == 1
    assert result["status"] == "UNKNOWN"
    assert "unresolved" in result["reason"].lower()
