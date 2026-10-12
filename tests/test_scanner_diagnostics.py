import time
import pytest
from app.marketdata.scanner import MarketScanner


class FakeExchange:
    def __init__(self, bids, asks):
        self.book = {"bids": bids, "asks": asks, "timestamp": time.time(), "source": "test"}

    async def get_order_book(self, symbol):
        return self.book


@pytest.mark.asyncio
async def test_scanner_exposes_route_and_book_diagnostics():
    scanner = MarketScanner({
        "binance": FakeExchange([[99.0, 10.0]], [[100.0, 10.0]]),
        "bybit": FakeExchange([[101.0, 10.0]], [[102.0, 10.0]]),
    })
    opportunities = await scanner.scan_opportunities("BTCUSDT", 10.0)
    diagnostic = scanner.diagnostics_by_symbol["BTCUSDT"]

    assert diagnostic["books_available"] == 2
    assert diagnostic["evaluated_routes"] == 2
    assert diagnostic["gross_positive_routes"] >= 1
    assert diagnostic["positive_opportunities"] == len(opportunities)
    assert opportunities
    assert opportunities[0]["buy_exchange"] == "binance"
    assert opportunities[0]["sell_exchange"] == "bybit"


@pytest.mark.asyncio
async def test_scanner_reports_stale_books_instead_of_silently_hiding_them():
    old_book = {"bids": [[99.0, 10.0]], "asks": [[100.0, 10.0]], "timestamp": time.time() - 30}
    class StaleExchange:
        async def get_order_book(self, symbol):
            return old_book

    scanner = MarketScanner({"binance": StaleExchange(), "bybit": StaleExchange()}, max_book_age_seconds=2)
    opportunities = await scanner.scan_opportunities("BTCUSDT", 10.0)
    diagnostic = scanner.diagnostics_by_symbol["BTCUSDT"]

    assert opportunities == []
    assert diagnostic["books_available"] == 0
    assert diagnostic["status"] == "waiting_for_books"
    assert set(diagnostic["stale_or_empty_exchanges"]) == {"binance", "bybit"}
