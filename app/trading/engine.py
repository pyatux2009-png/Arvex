import asyncio
import logging
import time
from typing import Any, Dict, Optional

logger = logging.getLogger("TradingEngine")


class TradingEngine:
    """Continuous scanner/executor loop.

    The engine never invents execution results. If an order cannot be confirmed,
    the executor returns UNKNOWN/UNRESOLVED and the engine records that state.
    """

    def __init__(self, scanner, executor, symbols, capital_usd: float,
                 interval_seconds: float = 0.25, cooldown_seconds: float = 2.0,
                 auto_execute: bool = False):
        self.scanner = scanner
        self.executor = executor
        self.symbols = list(symbols)
        self.capital_usd = float(capital_usd)
        self.interval_seconds = max(0.05, float(interval_seconds))
        self.cooldown_seconds = max(0.0, float(cooldown_seconds))
        self.auto_execute = bool(auto_execute)
        self.running = False
        self.task: Optional[asyncio.Task] = None
        self.last_scan_at = 0.0
        self.last_execution_at = 0.0
        self.last_opportunities = []
        self.last_result: Optional[Dict[str, Any]] = None
        self.execution_count = 0
        self.error_count = 0

    async def start(self):
        if self.running:
            return
        self.running = True
        self.task = asyncio.create_task(self._run(), name="arb-trading-engine")
        logger.info("Trading engine started auto_execute=%s", self.auto_execute)

    async def stop(self):
        self.running = False
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
            self.task = None
        logger.info("Trading engine stopped")

    async def scan_once(self):
        combined = []
        for symbol in self.symbols:
            try:
                combined.extend(await self.scanner.scan_opportunities(symbol, self.capital_usd))
            except Exception:
                self.error_count += 1
                logger.exception("Scan failed for %s", symbol)
        combined.sort(key=lambda x: (x.get("risk_level") == "SAFE_CANDIDATE",
                                     x.get("net_profit_usd", 0.0)), reverse=True)
        self.last_scan_at = time.time()
        self.last_opportunities = combined[:50]
        return self.last_opportunities

    async def _run(self):
        while self.running:
            try:
                opportunities = await self.scan_once()
                if self.auto_execute and opportunities and time.time() - self.last_execution_at >= self.cooldown_seconds:
                    for opportunity in opportunities:
                        if opportunity.get("risk_level") == "BLOCKED":
                            continue
                        if opportunity.get("net_profit_usd", 0.0) <= 0:
                            continue
                        result = await self.executor.execute_arbitrage(opportunity)
                        self.last_result = result
                        self.last_execution_at = time.time()
                        self.execution_count += 1
                        # Never fire multiple trades from the same scan.
                        break
            except asyncio.CancelledError:
                break
            except Exception:
                self.error_count += 1
                logger.exception("Trading engine loop error")
            await asyncio.sleep(self.interval_seconds)

    def status(self) -> Dict[str, Any]:
        return {
            "running": self.running,
            "auto_execute": self.auto_execute,
            "symbols": self.symbols,
            "capital_usd": self.capital_usd,
            "last_scan_at": self.last_scan_at,
            "last_execution_at": self.last_execution_at,
            "execution_count": self.execution_count,
            "error_count": self.error_count,
            "last_opportunities": self.last_opportunities[:10],
            "last_result": self.last_result,
        }
