import pytest

from app.trading.executor import TradeExecutor


class RulesExchange:
    def __init__(self, rules):
        self.rules = rules

    async def get_market_rules(self, symbol):
        assert symbol == "BTCUSDT"
        return self.rules


@pytest.mark.asyncio
async def test_execution_normalizes_ioc_prices_and_compatible_quantity_steps():
    exchanges = {
        "binance": RulesExchange({"qty_step": 0.003, "tick_size": 0.01}),
        "bybit": RulesExchange({"qty_step": 0.002, "tick_size": 0.01}),
    }
    executor = TradeExecutor(exchanges, mode="PAPER")
    result = await executor._prepare_execution_opportunity({
        "symbol": "BTCUSDT",
        "buy_exchange": "binance",
        "sell_exchange": "bybit",
        "quantity": 0.019,
        "buy_price": 100.0,
        "sell_price": 102.0,
        "buy_order_price": 100.003,
        "sell_order_price": 101.007,
        "slippage_pct": 0.01,
        "other_costs_usd": 0.0,
        "execution_supported": True,
    })

    assert result["allowed"] is True
    opportunity = result["opportunity"]
    # The smallest quantity step accepted by both 0.003 and 0.002 is 0.006.
    assert opportunity["quantity"] == pytest.approx(0.018)
    # Buy rounds up and sell rounds down, never making the limit more aggressive
    # than the raw VWAP estimate in a way that improves the displayed profit.
    assert opportunity["buy_price"] == pytest.approx(100.01)
    assert opportunity["sell_price"] == pytest.approx(101.00)
    assert opportunity["buy_order_price"] == opportunity["buy_price"]
    assert opportunity["sell_order_price"] == opportunity["sell_price"]
    assert opportunity["net_profit_usd"] > 0


@pytest.mark.asyncio
async def test_execution_blocks_route_if_conservative_ioc_prices_erase_profit():
    exchanges = {
        "binance": RulesExchange({"qty_step": 0.001, "tick_size": 0.01}),
        "bybit": RulesExchange({"qty_step": 0.001, "tick_size": 0.01}),
    }
    executor = TradeExecutor(exchanges, mode="PAPER")
    result = await executor._prepare_execution_opportunity({
        "symbol": "BTCUSDT",
        "buy_exchange": "binance",
        "sell_exchange": "bybit",
        "quantity": 0.01,
        "buy_price": 100.0,
        "sell_price": 100.02,
        "buy_order_price": 100.004,
        "sell_order_price": 100.006,
        "slippage_pct": 0.05,
        "other_costs_usd": 0.0,
        "execution_supported": True,
    })

    assert result["allowed"] is False
    assert "non-positive" in result["reason"]
