import time

import pytest

import app.exchanges.binance as binance_module
import app.exchanges.bybit as bybit_module
from app.exchanges.binance import BinanceExchange
from app.exchanges.bybit import BybitExchange


@pytest.mark.asyncio
async def test_binance_refreshes_stale_cached_book_via_rest(monkeypatch):
    exchange = BinanceExchange(paper_mode=False)
    exchange.orderbooks["BTCUSDT"] = {
        "symbol": "BTCUSDT",
        "bids": [[99.0, 1.0]],
        "asks": [[101.0, 1.0]],
        "timestamp": time.time() - 10.0,
        "source": "websocket",
    }

    async def fake_request_json(method, url, params=None, headers=None, data=None):
        assert method == "GET"
        assert url.endswith("/api/v3/depth")
        return {"bids": [["100", "2"]], "asks": [["101", "3"]]}

    monkeypatch.setattr(binance_module, "request_json", fake_request_json)
    book = await exchange.get_order_book("BTCUSDT")

    assert book["source"] == "rest"
    assert book["bids"] == [[100.0, 2.0]]
    assert book["timestamp"] >= time.time() - 1.0


@pytest.mark.asyncio
async def test_bybit_refreshes_stale_cached_book_via_rest(monkeypatch):
    exchange = BybitExchange(paper_mode=False)
    exchange.orderbooks["BTCUSDT"] = {
        "symbol": "BTCUSDT",
        "bids": [[99.0, 1.0]],
        "asks": [[101.0, 1.0]],
        "timestamp": time.time() - 10.0,
        "source": "websocket",
    }

    async def fake_request_json(method, url, params=None, headers=None, data=None):
        assert method == "GET"
        assert url.endswith("/v5/market/orderbook")
        return {"retCode": 0, "result": {"b": [["100", "2"]], "a": [["101", "3"]]}}

    monkeypatch.setattr(bybit_module, "request_json", fake_request_json)
    book = await exchange.get_order_book("BTCUSDT")

    assert book["source"] == "rest"
    assert book["bids"] == [[100.0, 2.0]]
    assert book["timestamp"] >= time.time() - 1.0
