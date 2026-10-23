import math
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
        "binance": RulesExchange({"status": "TRADING", "min_qty": 0.001, "qty_step": 0.003, "tick_size": 0.01, "min_notional": 5.0}),
        "bybit": RulesExchange({"status": "TRADING", "min_qty": 0.001, "qty_step": 0.002, "tick_size": 0.01, "min_notional": 5.0}),
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
        "binance": RulesExchange({"status": "TRADING", "min_qty": 0.001, "qty_step": 0.001, "tick_size": 0.01, "min_notional": 5.0}),
        "bybit": RulesExchange({"status": "TRADING", "min_qty": 0.001, "qty_step": 0.001, "tick_size": 0.01, "min_notional": 5.0}),
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



@pytest.mark.asyncio
async def test_execution_blocks_when_exchange_adapter_has_no_market_rules():
    class MissingRulesExchange:
        pass

    executor = TradeExecutor({
        "binance": MissingRulesExchange(),
        "bybit": RulesExchange({
            "status": "TRADING",
            "min_qty": 0.001,
            "qty_step": 0.001,
            "tick_size": 0.01,
            "min_notional": 5.0,
        }),
    }, mode="PAPER")
    result = await executor._prepare_execution_opportunity({
        "symbol": "BTCUSDT",
        "buy_exchange": "binance",
        "sell_exchange": "bybit",
        "quantity": 0.01,
        "buy_order_price": 100.0,
        "sell_order_price": 102.0,
        "slippage_pct": 0.01,
        "other_costs_usd": 0.0,
    })

    assert result["allowed"] is False
    assert "does not provide required market rules" in result["reason"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("bad_rules", "reason"),
    [
        ({"status": "TRADING", "min_qty": 0.001, "qty_step": 0.001, "tick_size": 0.01}, "missing required fields"),
        ({"status": "HALT", "min_qty": 0.001, "qty_step": 0.001, "tick_size": 0.01, "min_notional": 5.0}, "not trading"),
        ({"status": "TRADING", "min_qty": 0.001, "qty_step": 0.0, "tick_size": 0.01, "min_notional": 5.0}, "qty_step and tick_size"),
    ],
)
async def test_execution_blocks_incomplete_or_invalid_market_rules(bad_rules, reason):
    exchanges = {
        "binance": RulesExchange(bad_rules),
        "bybit": RulesExchange({
            "status": "TRADING",
            "min_qty": 0.001,
            "qty_step": 0.001,
            "tick_size": 0.01,
            "min_notional": 5.0,
        }),
    }
    executor = TradeExecutor(exchanges, mode="PAPER")
    result = await executor._prepare_execution_opportunity({
        "symbol": "BTCUSDT",
        "buy_exchange": "binance",
        "sell_exchange": "bybit",
        "quantity": 0.01,
        "buy_order_price": 100.0,
        "sell_order_price": 102.0,
        "slippage_pct": 0.01,
        "other_costs_usd": 0.0,
    })

    assert result["allowed"] is False
    assert reason in result["reason"]



@pytest.mark.asyncio
async def test_execution_preserves_configured_other_costs_when_recalculating(monkeypatch):
    from app.trading import executor as executor_module

    monkeypatch.setattr(executor_module, "OTHER_COSTS_USD", 10.0)
    rules = {
        "status": "TRADING",
        "min_qty": 0.001,
        "qty_step": 0.001,
        "tick_size": 0.01,
        "min_notional": 5.0,
    }
    executor = TradeExecutor({
        "binance": RulesExchange(rules),
        "bybit": RulesExchange(rules),
    }, mode="PAPER")

    result = await executor._prepare_execution_opportunity({
        "symbol": "BTCUSDT",
        "buy_exchange": "binance",
        "sell_exchange": "bybit",
        "quantity": 0.1,
        "buy_order_price": 100.0,
        "sell_order_price": 103.0,
        "slippage_pct": 0.01,
    })

    assert result["allowed"] is False
    assert "non-positive" in result["reason"]



@pytest.mark.asyncio
async def test_normalized_ioc_notional_stays_within_requested_cap():
    rules = {
        "status": "TRADING",
        "min_qty": 0.001,
        "qty_step": 0.001,
        "tick_size": 0.1,
        "min_notional": 0.0,
    }
    executor = TradeExecutor({
        "binance": RulesExchange(rules),
        "bybit": RulesExchange(rules),
    }, mode="PAPER")

    result = await executor._prepare_execution_opportunity({
        "symbol": "BTCUSDT",
        "buy_exchange": "binance",
        "sell_exchange": "bybit",
        "quantity": 1.0,
        "position_size": 100.0,
        "buy_price": 100.0,
        "sell_price": 103.0,
        "buy_order_price": 100.01,
        "sell_order_price": 103.09,
        "slippage_pct": 0.01,
        "other_costs_usd": 0.0,
    })

    assert result["allowed"] is True
    opportunity = result["opportunity"]
    assert opportunity["buy_price"] == pytest.approx(100.1)
    assert opportunity["quantity"] == pytest.approx(0.999)
    assert opportunity["position_size"] <= 100.0


@pytest.mark.asyncio
async def test_partial_buy_fill_is_rounded_to_sell_venue_step_before_hedging():
    class ExecutionExchange:
        def __init__(self, name, rules, balances):
            self.name = name
            self.rules = rules
            self.balances = balances
            self.submissions = []
            self.paper_mode = True

        async def get_market_rules(self, symbol):
            return self.rules

        async def get_balance(self):
            return dict(self.balances)

        async def get_order_book(self, symbol):
            return {"bids": [[99.0, 10.0]], "asks": [[100.0, 10.0]]}

        async def create_order(self, symbol, side, amount, price, client_order_id=None):
            self.submissions.append((side, amount, price))
            if self.name == "binance" and side == "buy":
                return {
                    "status": "PARTIALLY_FILLED",
                    "filled_amount": 0.015,
                    "avg_price": 100.0,
                    "client_order_id": client_order_id,
                }
            return {
                "status": "FILLED",
                "filled_amount": amount,
                "avg_price": price,
                "fee_usd": 0.0,
                "client_order_id": client_order_id,
            }

        async def get_order_status(self, symbol, order_id=None, client_order_id=None):
            return {"status": "UNKNOWN", "filled_amount": 0.0}

        async def cancel_order(self, symbol, order_id=None, client_order_id=None):
            return {"status": "CANCELED"}

    buy_rules = {
        "status": "TRADING",
        "min_qty": 0.001,
        "qty_step": 0.001,
        "tick_size": 0.01,
        "min_notional": 0.0,
    }
    sell_rules = {
        "status": "TRADING",
        "min_qty": 0.001,
        "qty_step": 0.01,
        "tick_size": 0.01,
        "min_notional": 0.0,
    }
    binance = ExecutionExchange("binance", buy_rules, {"USDT": 10000.0, "BTC": 0.0})
    bybit = ExecutionExchange("bybit", sell_rules, {"USDT": 10000.0, "BTC": 10.0})
    executor = TradeExecutor({"binance": binance, "bybit": bybit}, mode="PAPER")
    executor.safety_engine.max_position_usd = 100.0

    result = await executor.execute_arbitrage({
        "symbol": "BTCUSDT",
        "buy_exchange": "binance",
        "sell_exchange": "bybit",
        "quantity": 1.0,
        "position_size": 100.0,
        "buy_price": 100.0,
        "sell_price": 103.0,
        "buy_order_price": 100.0,
        "sell_order_price": 103.0,
        "net_profit_usd": 2.7,
        "net_profit_pct": 2.7,
        "slippage_pct": 0.01,
        "book_age": 0.1,
        "liquidity_ok": True,
        "risk_level": "SAFE_CANDIDATE",
        "execution_supported": True,
    })

    assert result["status"] == "PARTIAL_RECOVERY"
    # A 0.015 buy fill cannot be sold as 0.015 on a venue with a 0.01 step.
    assert bybit.submissions[0][0] == "sell"
    assert bybit.submissions[0][1] == pytest.approx(0.01)
    # The unsellable remainder is explicitly sent through recovery on the buy venue.
    assert binance.submissions[1][0] == "sell"
    assert binance.submissions[1][1] == pytest.approx(0.005)
    assert result["recovery"]["status"] == "RECOVERED"



def test_executor_fill_parser_rejects_fill_above_submitted_sell_quantity():
    assert math.isnan(TradeExecutor._parse_fill_amount(
        {"status": "FILLED", "filled_amount": 0.015},
        0.01,
    ))


def test_executor_fill_parser_rejects_non_finite_execution_values():
    assert math.isnan(TradeExecutor._parse_fill_amount(
        {"status": "FILLED", "filled_amount": float("inf")},
        1.0,
    ))
    assert math.isnan(TradeExecutor._reported_execution_price(
        {"avg_price": float("nan")},
        100.0,
    ))
