from app.marketdata.websocket import BybitOrderBookStream


def test_bybit_spot_subscriptions_are_batched_to_ten_topics():
    symbols = [
        "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "DOGEUSDT",
        "ADAUSDT", "LINKUSDT", "AVAXUSDT", "LTCUSDT", "BCHUSDT", "TRXUSDT",
        "DOTUSDT", "TONUSDT", "XLMUSDT", "UNIUSDT", "ATOMUSDT", "NEARUSDT",
        "ETCUSDT", "SUIUSDT", "FILUSDT", "AAVEUSDT", "ARBUSDT", "OPUSDT",
    ]

    batches = BybitOrderBookStream.subscription_batches(symbols, max_args=10)

    assert [len(batch) for batch in batches] == [10, 10, 4]
    assert all(len(batch) <= 10 for batch in batches)
    assert [topic for batch in batches for topic in batch] == [
        f"orderbook.50.{symbol}" for symbol in symbols
    ]
