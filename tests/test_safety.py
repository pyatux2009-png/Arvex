from app.safety.engine import SafetyEngine
from app.arbitrage.scoring import evaluate_risk_level


def test_safety_engine_validation():
    engine = SafetyEngine(max_daily_loss=10.0)

    # A safe candidate must contain enough verified data for fail-closed checks.
    safe_opp = {
        "risk_level": "SAFE_CANDIDATE",
        "net_profit_usd": 1.5,
        "net_profit_pct": 1.5,
        "slippage_pct": 0.05,
        "quantity": 0.01,
        "buy_price": 100.0,
        "book_age": 0.2,
        "liquidity_ok": True,
    }
    assert engine.validate_opportunity(safe_opp)["allowed"] is True

    # A blocked route is rejected even if the remaining fields are positive.
    blocked_opp = {**safe_opp, "risk_level": "BLOCKED"}
    assert engine.validate_opportunity(blocked_opp)["allowed"] is False


def test_evaluate_risk_level():
    # Старый стакан или низкая ликвидность должны возвращать BLOCKED
    assert evaluate_risk_level(net_profit_pct=1.0, age_seconds=3.5, liquidity_depth=50.0) == "BLOCKED"
    assert evaluate_risk_level(net_profit_pct=0.6, age_seconds=0.5, liquidity_depth=100.0) == "SAFE_CANDIDATE"
