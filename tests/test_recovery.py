import pytest
from app.recovery.engine import RecoveryEngine


@pytest.mark.asyncio
async def test_recovery_engine_fallback():
    engine = RecoveryEngine(max_recovery_time_seconds=0.5)
    result = await engine.handle_single_leg_exposure(
        success_exchange="Binance",
        symbol="BTCUSDT",
        amount=0.01,
        bought_price=50000.0,
        exchanges={},
    )
    assert result["status"] == "UNRESOLVED"
    assert result["realized_pnl"] == 0.0
