from app.config import DEFAULT_SYMBOLS


def test_default_symbol_universe_contains_liquid_large_caps():
    symbols = DEFAULT_SYMBOLS.split(",")

    assert len(symbols) == 24
    assert len(set(symbols)) == len(symbols)
    assert all(symbol.endswith("USDT") for symbol in symbols)
    assert {"BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"}.issubset(symbols)
    assert {"XRPUSDT", "ADAUSDT", "LINKUSDT", "AVAXUSDT", "LTCUSDT"}.issubset(symbols)
    assert {"BCHUSDT", "XLMUSDT", "UNIUSDT", "ATOMUSDT", "NEARUSDT"}.issubset(symbols)
    assert {"ETCUSDT", "SUIUSDT", "FILUSDT", "AAVEUSDT", "ARBUSDT", "OPUSDT"}.issubset(symbols)
