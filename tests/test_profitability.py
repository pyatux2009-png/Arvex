import pytest

from app.arbitrage.profitability import calculate_net_profit, calculate_realized_profit


def test_calculate_net_profit_positive():
    res = calculate_net_profit(buy_price=50000.0, sell_price=50500.0, volume=0.001)
    assert res["net_profit_usd"] > 0
    assert res["gross_profit_pct"] == 1.0
    assert res["buy_fee"] > 0
    assert res["sell_fee"] > 0
    assert res["net_profit_pct"] == pytest.approx(
        res["net_profit_usd"] / (50000.0 * 0.001) * 100.0
    )


def test_calculate_net_profit_negative_spread():
    # Цена покупки выше цены продажи — чистый результат обязан быть отрицательным.
    res = calculate_net_profit(buy_price=50500.0, sell_price=50000.0, volume=0.001)
    assert res["net_profit_usd"] < 0
    assert res["net_profit_pct"] < 0


def test_net_percentage_uses_buy_capital_with_asymmetric_fees():
    res = calculate_net_profit(
        buy_price=100.0,
        sell_price=101.0,
        volume=2.0,
        custom_buy_fee=0.001,
        custom_sell_fee=0.002,
        slippage_pct=0.1,
        other_costs_usd=0.03,
    )
    expected_net = (
        2.0 * 101.0
        - 2.0 * 100.0
        - 2.0 * 100.0 * 0.001
        - 2.0 * 101.0 * 0.002
        - 2.0 * 100.0 * 0.001
        - 0.03
    )
    assert res["net_profit_usd"] == pytest.approx(expected_net)
    assert res["net_profit_pct"] == pytest.approx(expected_net / 200.0 * 100.0)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"custom_buy_fee": -0.001},
        {"custom_sell_fee": 1.01},
        {"slippage_pct": -0.1},
        {"other_costs_usd": -0.01},
    ],
)
def test_rejects_invalid_cost_inputs(kwargs):
    with pytest.raises(ValueError):
        calculate_net_profit(
            buy_price=100.0,
            sell_price=101.0,
            volume=1.0,
            **kwargs,
        )


def test_legacy_positional_arguments_keep_sell_price_and_quantity():
    res = calculate_net_profit(100.0, 101.0, 2.0)
    assert res["gross_profit_usd"] == pytest.approx(2.0)
    assert res["gross_profit_pct"] == pytest.approx(1.0)


def test_realized_profit_uses_reported_fee_amounts():
    res = calculate_realized_profit(
        buy_price=100.0,
        sell_price=101.0,
        volume=2.0,
        buy_fee_usd=0.25,
        sell_fee_usd=0.30,
        other_costs_usd=0.05,
    )
    assert res["gross_profit_usd"] == pytest.approx(2.0)
    assert res["total_fees_usd"] == pytest.approx(0.55)
    assert res["net_profit_usd"] == pytest.approx(1.40)
    assert res["net_profit_pct"] == pytest.approx(0.70)
    assert res["fee_source"] == "exchange_reported"
