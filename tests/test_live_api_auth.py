from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api import routes


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("endpoint", "args"),
    [
        (routes.start_engine, ()),
        (routes.stop_engine, ()),
        (routes.set_capital, ({"capital_usd": 10},)),
    ],
)
async def test_live_mutating_endpoints_fail_closed_without_configured_token(
    monkeypatch, endpoint, args
):
    monkeypatch.setattr(routes, "settings", SimpleNamespace(live_trading=True))
    monkeypatch.delenv("LIVE_API_TOKEN", raising=False)

    with pytest.raises(HTTPException) as exc:
        await endpoint(*args, x_api_token=None)

    assert exc.value.status_code == 503
    assert "LIVE_API_TOKEN" in exc.value.detail


@pytest.mark.asyncio
async def test_live_engine_start_rejects_wrong_token(monkeypatch):
    monkeypatch.setattr(routes, "settings", SimpleNamespace(live_trading=True))
    monkeypatch.setenv("LIVE_API_TOKEN", "a-long-test-secret")

    with pytest.raises(HTTPException) as exc:
        await routes.start_engine(x_api_token="wrong-secret")

    assert exc.value.status_code == 401


def test_paper_mode_does_not_require_live_api_token(monkeypatch):
    monkeypatch.setattr(routes, "settings", SimpleNamespace(live_trading=False))
    monkeypatch.delenv("LIVE_API_TOKEN", raising=False)

    routes._require_live_api_token(None)



@pytest.mark.asyncio
async def test_executor_live_mode_requires_token_even_when_module_default_is_paper(monkeypatch):
    from app.trading import executor as executor_module

    class Exchange:
        paper_mode = False
        api_key = "test-key"

    monkeypatch.setattr(executor_module, "LIVE_TRADING", False)
    monkeypatch.delenv("LIVE_API_TOKEN", raising=False)
    executor = executor_module.TradeExecutor(
        {"binance": Exchange(), "bybit": Exchange()},
        mode="LIVE",
    )

    result = await executor.execute_arbitrage({
        "symbol": "BTCUSDT",
        "buy_exchange": "binance",
        "sell_exchange": "bybit",
        "quantity": 0.01,
        "buy_price": 100.0,
        "sell_price": 102.0,
        "net_profit_usd": 0.1,
    })

    assert result["status"] == "BLOCKED"
    assert "LIVE_API_TOKEN" in result["reason"]
