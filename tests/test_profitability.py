from app.arbitrage.profitability import calculate_net_profit

def test_calculate_net_profit_positive():
    res = calculate_net_profit(buy_price=50000.0, sell_price=50500.0, volume=0.001)
    assert res["net_profit_usd"] > 0
    assert res["gross_profit_pct"] == 1.0
    assert res["buy_fee"] > 0
    assert res["sell_fee"] > 0

def test_calculate_net_profit_negative_spread():
    # Цена покупки выше цены продажи — чистый результат обязан быть отрицательным
    res = calculate_net_profit(buy_price=50500.0, sell_price=50000.0, volume=0.001)
    assert res["net_profit_usd"] < 0
    assert res["net_profit_pct"] < 0