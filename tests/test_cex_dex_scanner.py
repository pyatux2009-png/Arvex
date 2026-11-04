from decimal import Decimal

import pytest

from app.cex_dex.binance_stream import BinanceBookTickerStream
from app.cex_dex.models import DexPoolSnapshot
from app.cex_dex.pancakeswap_v2 import BSC_CHAIN_ID, DEFAULT_USDT, DEFAULT_WBNB
from app.cex_dex.scanner import CexDexPaperScanner


def fixtures(book_age=0.0, pool_age=0.0):
    book = BinanceBookTickerStream.parse_message(
        {"s": "BNBUSDT", "b": "599", "B": "100", "a": "600", "A": "100"},
        received_at=100.0 - book_age,
    )
    pool = DexPoolSnapshot(
        BSC_CHAIN_ID, "0x" + "1" * 40, DEFAULT_WBNB, DEFAULT_USDT,
        Decimal("100"), Decimal("60000"), 18, 18, 25, 1, 100.0 - pool_age,
    )
    return book, pool


def test_scanner_quotes_both_directions_for_each_budget():
    book, pool = fixtures()
    scanner = CexDexPaperScanner(cex_fee_bps=10, gas_cost_usdt=Decimal("0.05"))
    quotes = scanner.scan(book, pool, [Decimal("10"), Decimal("25")], now=100.0)
    assert len(quotes) == 4
    assert {q["direction"] for q in quotes} == {
        "BUY_BINANCE_SELL_PANCAKESWAP", "BUY_PANCAKESWAP_SELL_BINANCE"
    }
    assert {q["quote_size_usdt"] for q in quotes} == {"10", "25"}
    assert all(q["mode"] == "PAPER" for q in quotes)
    assert all("net_profit_usdt" in q and "intermediate_bnb" in q for q in quotes)


def test_scanner_applies_fees_gas_and_pool_price_impact():
    book, pool = fixtures()
    scanner = CexDexPaperScanner(cex_fee_bps=100, gas_cost_usdt=Decimal("0.50"))
    quotes = scanner.scan(book, pool, [Decimal("10")], now=100.0)
    route_a, route_b = quotes
    assert Decimal(route_a["cex_fee_usdt"]) > 0
    assert Decimal(route_a["estimated_gas_usdt"]) == Decimal("0.50")
    assert Decimal(route_a["net_profit_usdt"]) < Decimal(route_a["output_usdt"]) - Decimal("10")
    assert Decimal(route_b["net_profit_usdt"]) < Decimal(route_b["output_usdt"]) - Decimal("10")


def test_scanner_marks_insufficient_binance_top_level_quantity():
    book = BinanceBookTickerStream.parse_message(
        {"s": "BNBUSDT", "b": "599", "B": "0.001", "a": "600", "A": "0.001"},
        received_at=100.0,
    )
    _, pool = fixtures()
    quotes = CexDexPaperScanner().scan(book, pool, [Decimal("100")], now=100.0)
    assert not quotes[0]["executable_at_top_of_book"]
    assert "ask top-level" in quotes[0]["rejection_reason"]
    assert not quotes[1]["executable_at_top_of_book"]


def test_scanner_rejects_stale_data_and_invalid_sizes():
    book, pool = fixtures(book_age=10)
    scanner = CexDexPaperScanner(stale_after_seconds=5)
    assert scanner.scan(book, pool, [Decimal("10")], now=100.0) == []
    book, pool = fixtures()
    with pytest.raises(ValueError, match="positive"):
        scanner.scan(book, pool, [Decimal("0")], now=100.0)


def test_scanner_handles_reverse_pool_token_order():
    book, pool = fixtures()
    reversed_pool = DexPoolSnapshot(
        56, pool.pair_address, DEFAULT_USDT, DEFAULT_WBNB,
        pool.reserve1, pool.reserve0, 18, 18, 25, 1, 100.0,
    )
    quotes = CexDexPaperScanner().scan(book, reversed_pool, [Decimal("10")], now=100.0)
    assert len(quotes) == 2
