import os

from app.config import settings
from app.exchanges.binance import BinanceExchange
from app.exchanges.bybit import BybitExchange
from app.exchanges.public_marketdata import KrakenMarketDataExchange, OkxMarketDataExchange
from app.marketdata.scanner import MarketScanner
from app.marketdata.manager import MarketDataManager
from app.trading.executor import TradeExecutor
from app.trading.engine import TradingEngine


class Runtime:
    def __init__(self):
        paper = settings.trading_mode != "LIVE"
        # Only these adapters can ever be passed to the executor.
        self.trade_exchanges = {
            "binance": BinanceExchange(
                paper_mode=paper, testnet=settings.binance_testnet, market_data_live=True
            ),
            "bybit": BybitExchange(
                paper_mode=paper, testnet=settings.bybit_testnet, market_data_live=True
            ),
        }
        # OKX/Kraken are read-only discovery venues until their execution,
        # balances, lot sizes, fees and order lifecycle are independently tested.
        self.market_exchanges = {
            **self.trade_exchanges,
            "okx": OkxMarketDataExchange(),
            "kraken": KrakenMarketDataExchange(),
        }
        self.exchanges = self.trade_exchanges  # compatibility for existing callers
        self.scanner = MarketScanner(
            self.market_exchanges,
            max_book_age_seconds=settings.book_max_age_seconds,
            estimated_slippage_pct=settings.estimated_slippage_pct,
            execution_exchanges=self.trade_exchanges.keys(),
        )
        self.executor = TradeExecutor(self.trade_exchanges, mode=settings.trading_mode)
        self.streams = MarketDataManager(self.market_exchanges, settings.symbols)
        auto_execute = os.getenv("AUTO_EXECUTE", "false").strip().lower() in {"1", "true", "yes", "on"}
        # Live execution remains opt-in twice and is never enabled by this change.
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
