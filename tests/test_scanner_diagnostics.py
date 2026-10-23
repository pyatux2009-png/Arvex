import time

import pytest

from app.marketdata.scanner import MarketScanner


class FakeExchange:
    def __init__(self, bids, asks, timestamp=None, source="test"):
        self.book = {
            "bids": bids,
            "asks": asks,
            "timestamp": time.time() if timestamp is None else timestamp,
            "source": source,
        }

    async def get_order_book(self, symbol):
        return dict(self.book)


@pytest.mark.asyncio
async def test_scanner_reports_spread_erased_by_fees_and_slippage():
    exchanges = {
        "binance": FakeExchange([[99.9, 10]], [[100.0, 10]]),
        "bybit": FakeExchange([[100.15, 10]], [[100.25, 10]]),
    }
    scanner = MarketScanner(exchanges, estimated_slippage_pct=0.05)

    opportunities = await scanner.scan_opportunities("BTCUSDT", 50)
    diagnostic = scanner.diagnostics_by_symbol["BTCUSDT"]

    assert opportunities == []
    assert diagnostic["books_available"] == 2
    assert diagnostic["evaluated_routes"] == 2
    assert diagnostic["gross_positive_routes"] == 1
    assert diagnostic["nonpositive_net_routes"] >= 1
    assert diagnostic["status"] == "spread_erased_by_costs"
    assert diagnostic["best_gross_candidate"] is not None


@pytest.mark.asyncio
async def test_scanner_finds_positive_liquid_route_and_marks_execution_support():
    exchanges = {
        "binance": FakeExchange([[99.0, 10]], [[100.0, 10]]),
        "bybit": FakeExchange([[103.0, 10]], [[104.0, 10]]),
    }
    scanner = MarketScanner(exchanges, estimated_slippage_pct=0.01, execution_exchanges={"binance", "bybit"})

    opportunities = await scanner.scan_opportunities("BTCUSDT", 50)

    assert opportunities
    best = opportunities[0]
    assert best["buy_exchange"] == "binance"
    assert best["sell_exchange"] == "bybit"
    assert best["net_profit_usd"] > 0
    assert best["net_profit_pct"] == pytest.approx(best["net_profit_usd"] / best["position_size"] * 100, abs=1e-6)
    assert best["liquidity_ok"] is True
    assert best["execution_supported"] is True
    assert scanner.diagnostics_by_symbol["BTCUSDT"]["status"] == "opportunities_found"


@pytest.mark.asyncio
async def test_scanner_excludes_stale_book_and_explains_why():
    exchanges = {
        "binance": FakeExchange([[99.0, 10]], [[100.0, 10]], timestamp=time.time() - 20),
        "bybit": FakeExchange([[103.0, 10]], [[104.0, 10]]),
    }
    scanner = MarketScanner(exchanges, max_book_age_seconds=2.0)

    opportunities = await scanner.scan_opportunities("BTCUSDT", 50)

    assert opportunities == []
    diagnostic = scanner.diagnostics_by_symbol["BTCUSDT"]
    assert diagnostic["books_available"] == 1
    assert diagnostic["status"] == "waiting_for_books"
    assert diagnostic["stale_or_empty_exchanges"]["binance"] == "stale_book"


@pytest.mark.asyncio
async def test_scanner_rejects_crossed_book():
    exchanges = {
        "binance": FakeExchange([[101.0, 10]], [[100.0, 10]]),
        "bybit": FakeExchange([[99.0, 10]], [[100.0, 10]]),
    }
    scanner = MarketScanner(exchanges)

    opportunities = await scanner.scan_opportunities("BTCUSDT", 50)

    assert opportunities == []
    assert scanner.diagnostics_by_symbol["BTCUSDT"]["stale_or_empty_exchanges"]["binance"] == "crossed_or_invalid_book"


@pytest.mark.asyncio
async def test_market_data_only_route_is_not_marked_executable():
    exchanges = {
        "binance": FakeExchange([[99.0, 10]], [[100.0, 10]]),
        "okx": FakeExchange([[103.0, 10]], [[104.0, 10]]),
    }
    scanner = MarketScanner(exchanges, estimated_slippage_pct=0.01, execution_exchanges={"binance", "bybit"})

    opportunities = await scanner.scan_opportunities("BTCUSDT", 50)

    assert opportunities
    assert opportunities[0]["execution_supported"] is False


@pytest.mark.asyncio
async def test_auto_execute_skips_discovery_only_route():
    from app.trading.engine import TradingEngine

    class Scanner:
        async def scan_opportunities(self, symbol, capital):
            return [{
                "symbol": symbol, "buy_exchange": "binance", "sell_exchange": "okx",
                "net_profit_usd": 1.0, "net_profit_pct": 1.0, "risk_level": "NORMAL",
                "execution_supported": False,
            }]

    class Executor:
        def __init__(self):
            self.calls = 0

        async def execute_arbitrage(self, opportunity):
            self.calls += 1
            return {"status": "FILLED"}

    executor = Executor()
    engine = TradingEngine(Scanner(), executor, ["BTCUSDT"], 50, interval_seconds=0.01, auto_execute=True)
    await engine.start()
    await __import__("asyncio").sleep(0.04)
    await engine.stop()

    assert executor.calls == 0
    assert engine.execution_count == 0


@pytest.mark.asyncio
async def test_okx_public_adapter_parses_order_book(monkeypatch):
    from app.exchanges import public_marketdata

    async def fake_request_json(method, url, **kwargs):
        assert "okx.com" in url
        assert kwargs["params"]["instId"] == "BTC-USDT"
        return {"code": "0", "data": [{"bids": [["99.0", "2"]], "asks": [["100.0", "3"]]}]}

    monkeypatch.setattr(public_marketdata, "request_json", fake_request_json)
    exchange = public_marketdata.OkxMarketDataExchange()
    book = await exchange.get_order_book("BTCUSDT")

    assert book["bids"] == [[99.0, 2.0]]
    assert book["asks"] == [[100.0, 3.0]]
    assert book["source"] == "rest"


@pytest.mark.asyncio
async def test_kraken_public_adapter_parses_order_book(monkeypatch):
    from app.exchanges import public_marketdata

    async def fake_request_json(method, url, **kwargs):
        assert "kraken.com" in url
        return {"error": [], "result": {"XXBTZUSDT": {"bids": [["99.0", "2", 1]], "asks": [["100.0", "3", 1]]}}}

    monkeypatch.setattr(public_marketdata, "request_json", fake_request_json)
    exchange = public_marketdata.KrakenMarketDataExchange()
    book = await exchange.get_order_book("BTCUSDT")

    assert book["bids"] == [[99.0, 2.0]]
    assert book["asks"] == [[100.0, 3.0]]
    assert book["source"] == "rest"


def test_kraken_websocket_book_merge_updates_and_deletes_levels():
    from app.marketdata.websocket import KrakenOrderBookStream

    snapshot_bids = [{"price": "99", "qty": "2"}, {"price": "98", "qty": "3"}]
    bids = KrakenOrderBookStream._merge([], snapshot_bids, reverse=True, snapshot=True)
    updated = KrakenOrderBookStream._merge(
        bids,
        [{"price": "99", "qty": "0"}, {"price": "100", "qty": "1"}],
        reverse=True,
    )

    assert updated == [[100.0, 1.0], [98.0, 3.0]]



@pytest.mark.asyncio
async def test_scanner_emits_worst_book_prices_for_ioc_limits():
    exchanges = {
        "binance": FakeExchange([[99.0, 10]], [[100.0, 10], [101.0, 10]]),
        "bybit": FakeExchange([[103.0, 10], [102.0, 10]], [[104.0, 10]]),
    }
    scanner = MarketScanner(exchanges, estimated_slippage_pct=0.01, execution_exchanges={"binance", "bybit"})
    opportunities = await scanner.scan_opportunities("BTCUSDT", 50)

    route = next(item for item in opportunities if item["buy_exchange"] == "binance" and item["sell_exchange"] == "bybit")
    assert route["buy_price"] == pytest.approx(100.0)
    assert route["sell_price"] == pytest.approx(103.0)
    assert route["buy_order_price"] == pytest.approx(100.0)
    assert route["sell_order_price"] == pytest.approx(103.0)
