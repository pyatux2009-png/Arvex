import os
from app.config import settings
from app.exchanges.binance import BinanceExchange
from app.exchanges.bybit import BybitExchange
from app.marketdata.scanner import MarketScanner
from app.marketdata.manager import MarketDataManager
from app.trading.executor import TradeExecutor
from app.trading.engine import TradingEngine


class Runtime:
    def __init__(self):
        paper = settings.trading_mode != "LIVE"
        self.exchanges = {
            "binance": BinanceExchange(paper_mode=paper, testnet=settings.binance_testnet, market_data_live=True),
            "bybit": BybitExchange(paper_mode=paper, testnet=settings.bybit_testnet, market_data_live=True),
        }
        self.scanner = MarketScanner(self.exchanges)
        self.executor = TradeExecutor(self.exchanges, mode=settings.trading_mode)
        self.streams = MarketDataManager(self.exchanges, settings.symbols)
        auto_execute = os.getenv("AUTO_EXECUTE", "false").strip().lower() in {"1", "true", "yes", "on"}
        # Live is intentionally opt-in twice: TRADING_MODE=LIVE and AUTO_EXECUTE=true.
        self.engine = TradingEngine(
            self.scanner,
            self.executor,
            settings.symbols,
            settings.max_trade_size_usd,
            interval_seconds=float(os.getenv("SCAN_INTERVAL_SECONDS", "0.25")),
            cooldown_seconds=float(os.getenv("TRADE_COOLDOWN_SECONDS", "2.0")),
            auto_execute=auto_execute,
        )
        self.started = False

    async def start(self):
        if self.started:
            return
        await self.streams.start()
        await self.engine.start()
        self.started = True

    async def stop(self):
        if not self.started:
            return
        await self.engine.stop()
        await self.streams.stop()
        self.started = False


_runtime = None


def get_runtime():
    global _runtime
    if _runtime is None:
        _runtime = Runtime()
    return _runtime
