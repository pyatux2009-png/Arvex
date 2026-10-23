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
