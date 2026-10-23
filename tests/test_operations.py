import json

import pytest

from app import operations


def test_emergency_stop_persists_across_reads(tmp_path, monkeypatch):
    state_file = tmp_path / "state.json"
    monkeypatch.setenv("ARVEX_STATE_PATH", str(state_file))

    assert operations.emergency_stop_enabled() is False
    assert operations.set_emergency_stop(True) == {"emergency_stop": True}
    assert operations.emergency_stop_enabled() is True
    assert json.loads(state_file.read_text(encoding="utf-8"))["emergency_stop"] is True

    operations.set_emergency_stop(False)
    assert operations.emergency_stop_enabled() is False


def test_invalid_state_fails_safe_and_cannot_be_cleared(tmp_path, monkeypatch):
    state_file = tmp_path / "state.json"
    state_file.write_text("{invalid json", encoding="utf-8")
    monkeypatch.setenv("ARVEX_STATE_PATH", str(state_file))

    assert operations.emergency_stop_enabled() is True
    with pytest.raises(RuntimeError, match="state file is invalid"):
        operations.set_emergency_stop(False)

    # Explicitly setting the stop is allowed and repairs the state file safely.
    operations.set_emergency_stop(True)
    assert operations.emergency_stop_enabled() is True



@pytest.mark.asyncio
async def test_engine_emergency_stop_blocks_auto_execution():
    import asyncio

    from app.trading.engine import TradingEngine

    class Scanner:
        async def scan_opportunities(self, symbol, capital):
            return [{
                "symbol": symbol,
                "net_profit_usd": 1.0,
                "net_profit_pct": 1.0,
                "risk_level": "SAFE_CANDIDATE",
                "execution_supported": True,
            }]

    class Executor:
        def __init__(self):
            self.calls = 0

        async def execute_arbitrage(self, opportunity):
            self.calls += 1
            return {"status": "FILLED"}

    executor = Executor()
    engine = TradingEngine(
        Scanner(), executor, ["BTCUSDT"], 10.0,
        interval_seconds=0.05, auto_execute=True,
    )
    engine.emergency_stop = True
    await engine.start()
    try:
        await asyncio.sleep(0.12)
    finally:
        await engine.stop()

    assert executor.calls == 0
    assert engine.status()["emergency_stop"] is True
