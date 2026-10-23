import pytest

from app.trading.executor import TradeExecutor


@pytest.mark.asyncio
async def test_executor_blocks_discovery_only_venue():
    executor = TradeExecutor({"binance": object(), "bybit": object()}, mode="PAPER")
    result = await executor.execute_arbitrage({
        "symbol": "BTCUSDT",
        "buy_exchange": "binance",
        "sell_exchange": "okx",
        "quantity": 0.01,
        "buy_price": 100.0,
        "sell_price": 110.0,
        "net_profit_usd": 0.1,
        "net_profit_pct": 1.0,
        "slippage_pct": 0.01,
        "book_age": 0.1,
        "liquidity_ok": True,
        "risk_level": "SAFE_CANDIDATE",
    })
    assert result["status"] == "BLOCKED"
    assert "execution-enabled" in result["reason"]


@pytest.mark.asyncio
async def test_executor_blocks_non_usdt_symbol():
    executor = TradeExecutor({"binance": object(), "bybit": object()}, mode="PAPER")
    result = await executor.execute_arbitrage({
        "symbol": "BTCUSD",
        "buy_exchange": "binance",
        "sell_exchange": "bybit",
        "quantity": 0.01,
        "buy_price": 100.0,
        "sell_price": 110.0,
        "net_profit_usd": 0.1,
        "net_profit_pct": 1.0,
        "slippage_pct": 0.01,
        "book_age": 0.1,
        "liquidity_ok": True,
        "risk_level": "SAFE_CANDIDATE",
    })
    assert result["status"] == "BLOCKED"
    assert "USDT-quoted" in result["reason"]


@pytest.mark.asyncio
async def test_executor_blocks_live_mode_without_live_api_token(monkeypatch):
    import app.trading.executor as executor_module

    monkeypatch.setattr(executor_module, "LIVE_TRADING", True)
    monkeypatch.delenv("LIVE_API_TOKEN", raising=False)
    executor = TradeExecutor({}, mode="LIVE")
    result = await executor.execute_arbitrage({})
    assert result["status"] == "BLOCKED"
    assert "LIVE_API_TOKEN" in result["reason"]
