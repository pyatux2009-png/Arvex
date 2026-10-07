import pytest
from app.trading.engine import TradingEngine
from app.marketdata.scanner import MarketScanner
from app.exchanges.binance import BinanceExchange


@pytest.mark.asyncio
async def test_trading_engine_start_stop():
    ex = BinanceExchange(paper_mode=True)
    scanner = MarketScanner({'binance': ex})
    class Executor:
        async def execute_arbitrage(self, opportunity):
            return {'status': 'FILLED'}
    engine = TradingEngine(scanner, Executor(), ['BTCUSDT'], 50, interval_seconds=0.05, auto_execute=False)
    await engine.start()
    await __import__('asyncio').sleep(0.08)
    assert engine.running is True
    await engine.stop()
    assert engine.running is False
    assert engine.last_scan_at > 0
