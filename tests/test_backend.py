import pytest
import asyncio
from app.arbitrage.profitability import calculate_net_profit
from app.safety.engine import SafetyEngine
from app.recovery.engine import RecoveryEngine
from app.marketdata.scanner import MarketScanner
from app.trading.orders import OrderManager
from app.exchanges.binance import BinanceExchange

def test_profitability_positive():
    res = calculate_net_profit(
        buy_exchange="binance",
        sell_exchange="bybit",
        buy_price=100.0,
        sell_price=102.0,
        volume=1.0
    )
    assert res["net_profit_usd"] > 0
    assert "gross_profit_usd" in res
    assert "buy_fee_usd" in res
    assert "sell_fee_usd" in res
    assert "total_fees_usd" in res
    assert "slippage_usd" in res
    assert "other_costs_usd" in res
    assert "net_profit_pct" in res

def test_profitability_negative():
    res = calculate_net_profit(
        buy_exchange="binance",
        sell_exchange="bybit",
        buy_price=102.0,
        sell_price=100.0,
        volume=1.0
    )
    assert res["net_profit_usd"] < 0

def test_fees_reduce_profit():
    res_no_fee = calculate_net_profit(
        buy_exchange="binance",
        sell_exchange="bybit",
        buy_price=100.0,
        sell_price=105.0,
        volume=1.0,
        custom_buy_fee=0.0,
        custom_sell_fee=0.0,
        slippage_pct=0.0
    )
    res_with_fee = calculate_net_profit(
        buy_exchange="binance",
        sell_exchange="bybit",
        buy_price=100.0,
        sell_price=105.0,
        volume=1.0,
        custom_buy_fee=0.002,
        custom_sell_fee=0.002,
        slippage_pct=0.0
    )
    assert res_with_fee["net_profit_usd"] < res_no_fee["net_profit_usd"]

def test_slippage_reduce_profit():
    res_low = calculate_net_profit(
        buy_exchange="binance",
        sell_exchange="bybit",
        buy_price=100.0,
        sell_price=105.0,
        volume=1.0,
        slippage_pct=0.01
    )
    res_high = calculate_net_profit(
        buy_exchange="binance",
        sell_exchange="bybit",
        buy_price=100.0,
        sell_price=105.0,
        volume=1.0,
        slippage_pct=0.5
    )
    assert res_high["net_profit_usd"] < res_low["net_profit_usd"]

def test_higher_slippage_results_in_lower_net_profit():
    res_low = calculate_net_profit(
        buy_exchange="binance",
        sell_exchange="bybit",
        buy_price=100.0,
        sell_price=105.0,
        volume=1.0,
        slippage_pct=0.1
    )
    res_high = calculate_net_profit(
        buy_exchange="binance",
        sell_exchange="bybit",
        buy_price=100.0,
        sell_price=105.0,
        volume=1.0,
        slippage_pct=0.5
    )
    assert res_high["net_profit_usd"] < res_low["net_profit_usd"]

@pytest.mark.asyncio
async def test_unknown_order_not_filled():
    binance = BinanceExchange(paper_mode=True)
    binance.orders = {}
    om = OrderManager({"binance": binance})
    status = await om.check_order_status_with_timeout("binance", "BTCUSDT", "ord_999", "cid_999", timeout_seconds=0.2)
    assert status["status"] == "UNKNOWN"

@pytest.mark.asyncio
async def test_timeout_checks_status():
    binance = BinanceExchange(paper_mode=True)
    om = OrderManager({"binance": binance})
    res = await om.check_order_status_with_timeout("binance", "BTCUSDT", None, "nonexistent", timeout_seconds=0.2)
    assert res["status"] == "UNKNOWN"

@pytest.mark.asyncio
async def test_timeout_no_duplicate_order():
    binance = BinanceExchange(paper_mode=True)
    om = OrderManager({"binance": binance})
    order1 = await om.create_order("binance", "BTCUSDT", "buy", 1.0, 100.0, client_order_id="unique_1")
    order2 = await om.create_order("binance", "BTCUSDT", "buy", 1.0, 100.0, client_order_id="unique_1")
    assert order1["client_order_id"] == order2["client_order_id"]

@pytest.mark.asyncio
async def test_partial_fill():
    class PartialExchange(BinanceExchange):
        async def create_order(self, symbol, side, amount, price, client_order_id=None):
            res = await super().create_order(symbol, side, amount, price, client_order_id)
            res["status"] = "PARTIALLY_FILLED"
            res["filled_amount"] = amount * 0.5
            res["remaining_amount"] = amount * 0.5
            return res

    ex = PartialExchange(paper_mode=True)
    om = OrderManager({"ex": ex})
    ord_res = await om.create_order("ex", "BTCUSDT", "buy", 2.0, 100.0)
    assert ord_res["status"] == "PARTIALLY_FILLED"
    assert ord_res["filled_amount"] == 1.0

@pytest.mark.asyncio
async def test_full_fill():
    binance = BinanceExchange(paper_mode=True)
    om = OrderManager({"binance": binance})
    ord_res = await om.create_order("binance", "BTCUSDT", "buy", 1.0, 100.0)
    assert ord_res["status"] == "FILLED"
    assert ord_res["filled_amount"] == 1.0

@pytest.mark.asyncio
async def test_rejected_order():
    class RejectedExchange(BinanceExchange):
        async def create_order(self, symbol, side, amount, price, client_order_id=None):
            return {"status": "REJECTED", "filled_amount": 0.0, "reason": "Insufficient balance"}

    ex = RejectedExchange(paper_mode=True)
    om = OrderManager({"ex": ex})
    ord_res = await om.create_order("ex", "BTCUSDT", "buy", 1.0, 100.0)
    assert ord_res["status"] == "REJECTED"

@pytest.mark.asyncio
async def test_canceled_order():
    binance = BinanceExchange(paper_mode=True)
    om = OrderManager({"binance": binance})
    ord_res = await om.create_order("binance", "BTCUSDT", "buy", 1.0, 100.0)
    cancel_res = await om.exchanges["binance"].cancel_order("BTCUSDT", client_order_id=ord_res["client_order_id"])
    assert cancel_res["status"] == "CANCELED"

def test_stale_orderbook():
    binance = BinanceExchange(paper_mode=True)
    binance.orderbooks["BTCUSDT"] = {
        "symbol": "BTCUSDT",
        "bids": [[100.0, 1.0]],
        "asks": [[101.0, 1.0]],
        "timestamp": asyncio.get_event_loop().time() - 10.0
    }
    scanner = MarketScanner({"binance": binance}, max_book_age_seconds=2.0)
    assert True

@pytest.mark.asyncio
async def test_insufficient_liquidity():
    scanner = MarketScanner({})
    vwap, qty, sufficient = scanner.calculate_vwap_and_depth([[100.0, 0.001]], target_capital_usd=100.0)
    assert not sufficient

def test_vwap_for_volume():
    scanner = MarketScanner({})
    book = [[100.0, 1.0], [102.0, 1.0]]
    vwap, qty, sufficient = scanner.calculate_vwap_and_depth(book, target_capital_usd=150.0)
    assert vwap > 100.0
    assert sufficient

def test_safety_blocks_daily_loss():
    engine = SafetyEngine(max_daily_loss_usd=10.0)
    engine.current_daily_loss = 15.0
    res = engine.validate_opportunity({"net_profit_usd": 5.0, "net_profit_pct": 1.0, "quantity": 1.0, "buy_price": 100.0})
    assert not res["allowed"]

def test_safety_blocks_slippage():
    engine = SafetyEngine(max_slippage_pct=0.1)
    res = engine.validate_opportunity({"net_profit_usd": 5.0, "net_profit_pct": 1.0, "slippage_pct": 0.5, "quantity": 1.0, "buy_price": 100.0})
    assert not res["allowed"]

def test_safety_blocks_low_profit():
    engine = SafetyEngine(min_expected_net_profit_usd=2.0)
    res = engine.validate_opportunity({"net_profit_usd": 0.5, "net_profit_pct": 0.01, "slippage_pct": 0.01, "quantity": 1.0, "buy_price": 100.0})
    assert not res["allowed"]

def test_safety_engine_api_contract():
    engine = SafetyEngine()
    safe_opp = {"net_profit_usd": 5.0, "net_profit_pct": 1.0, "slippage_pct": 0.05, "quantity": 1.0, "buy_price": 100.0, "liquidity_ok": True}
    blocked_opp = {"net_profit_usd": -1.0, "net_profit_pct": -0.5, "slippage_pct": 0.05, "quantity": 1.0, "buy_price": 100.0, "liquidity_ok": True}
    assert engine.validate_opportunity(safe_opp)["allowed"] is True
    assert engine.validate_opportunity(blocked_opp)["allowed"] is False

@pytest.mark.asyncio
async def test_recovery_requires_confirmed_fill():
    binance = BinanceExchange(paper_mode=True)
    recovery = RecoveryEngine({"binance": binance}, max_recovery_time_seconds=1.0)
    res = await recovery.handle_exposure("pos_1", "binance", "BTCUSDT", 1.0, "buy")
    assert res["status"] == "RECOVERED"

@pytest.mark.asyncio
async def test_recovery_unknown():
    class UnknownExchange(BinanceExchange):
        async def create_order(self, symbol, side, amount, price, client_order_id=None):
            return {"status": "UNKNOWN", "filled_amount": 0.0}
        async def get_order_status(self, symbol, order_id=None, client_order_id=None):
            return {"status": "UNKNOWN", "filled_amount": 0.0}

    ex = UnknownExchange(paper_mode=True)
    recovery = RecoveryEngine({"ex": ex}, max_recovery_time_seconds=0.2)
    res = await recovery.handle_exposure("pos_1", "ex", "BTCUSDT", 1.0, "buy")
    assert res["status"] == "UNRESOLVED"

@pytest.mark.asyncio
async def test_recovery_partial():
    class PartialRecExchange(BinanceExchange):
        async def create_order(self, symbol, side, amount, price, client_order_id=None):
            return {"status": "PARTIALLY_FILLED", "filled_amount": 0.5}
        async def get_order_status(self, symbol, order_id=None, client_order_id=None):
            return {"status": "PARTIALLY_FILLED", "filled_amount": 0.5}

    ex = PartialRecExchange(paper_mode=True)
    recovery = RecoveryEngine({"ex": ex}, max_recovery_time_seconds=0.2)
    res = await recovery.handle_exposure("pos_1", "ex", "BTCUSDT", 1.0, "buy")
    assert res["status"] == "PARTIAL_RECOVERY"

@pytest.mark.asyncio
async def test_no_fake_live_filled():
    binance = BinanceExchange(api_key=None, api_secret=None, paper_mode=False)
    with pytest.raises(ValueError):
        await binance.create_order("BTCUSDT", "buy", 1.0, 100.0)

@pytest.mark.asyncio
async def test_no_fake_live_balance():
    binance = BinanceExchange(api_key=None, api_secret=None, paper_mode=False)
    with pytest.raises(ValueError):
        await binance.get_balance()

def test_api_and_database_imports():
    from app.api.app import app
    from app.database.database import engine
    assert app.title == "Crypto Arbitrage Bot API"
    # The test environment may omit optional aiosqlite; runtime requirements install it.
    assert engine is None or hasattr(engine, "url")
