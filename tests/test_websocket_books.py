from app.marketdata.websocket import BybitOrderBookStream


class DummyExchange:
    def __init__(self):
        self.orderbooks = {}


def test_bybit_book_merge_sorts_levels_and_applies_deletions():
    bids = BybitOrderBookStream._apply(
        [[100.0, 1.0], [99.0, 2.0]],
        [["101", "3"], ["100", "0"]],
        reverse=True,
    )
    asks = BybitOrderBookStream._apply(
        [[102.0, 1.0], [103.0, 2.0]],
        [["101", "4"], ["103", "0"]],
        reverse=False,
    )

    assert bids == [[101.0, 3.0], [99.0, 2.0]]
    assert asks == [[101.0, 4.0], [102.0, 1.0]]


def test_bybit_stream_starts_without_a_falsely_initialized_book():
    stream = BybitOrderBookStream(DummyExchange(), ["BTCUSDT"])

    assert stream.books == {}
    assert stream.initialized == set()
    assert "BTCUSDT" not in stream.exchange.orderbooks
