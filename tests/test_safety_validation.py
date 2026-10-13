import pytest

from app.safety.engine import SafetyEngine


def valid_opportunity():
    return {
        "risk_level": "SAFE_CANDIDATE",
        "net_profit_usd": 1.0,
        "net_profit_pct": 1.0,
        "slippage_pct": 0.05,
        "quantity": 0.1,
        "buy_price": 100.0,
        "book_age": 0.1,
        "liquidity_ok": True,
    }


@pytest.mark.parametrize("field,value", [
    ("net_profit_usd", float("nan")),
    ("net_profit_pct", float("inf")),
    ("slippage_pct", float("nan")),
    ("quantity", float("inf")),
    ("buy_price", float("nan")),
])
def test_safety_rejects_non_finite_values(field, value):
    opportunity = valid_opportunity()
    opportunity[field] = value

    result = SafetyEngine().validate_opportunity(opportunity)

    assert result["allowed"] is False
    assert "invalid opportunity data" in result["reason"].lower()


def test_safety_rejects_missing_liquidity_confirmation():
    opportunity = valid_opportunity()
    opportunity.pop("liquidity_ok")

    result = SafetyEngine().validate_opportunity(opportunity)

    assert result["allowed"] is False
    assert "liquidity" in result["reason"].lower()


def test_safety_rejects_zero_quantity():
    opportunity = valid_opportunity()
    opportunity["quantity"] = 0.0

    result = SafetyEngine().validate_opportunity(opportunity)

    assert result["allowed"] is False
    assert "must be positive" in result["reason"].lower()
