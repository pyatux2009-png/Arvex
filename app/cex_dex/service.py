import asyncio
import time
from typing import Optional

from app.cex_dex.binance_stream import BinanceBookTickerStream
from app.cex_dex.pancakeswap_v2 import PancakeSwapV2Client


class CexDexMarketDataService:
    """Runs read-only Binance and PancakeSwap feeds for PAPER research."""

    def __init__(self, rpc_url: str, symbol: str = "BNBUSDT", dex_poll_seconds: float = 2.0, stale_after_seconds: float = 5.0):
        if dex_poll_seconds <= 0 or stale_after_seconds <= 0:
            raise ValueError("poll and stale intervals must be positive")
        self.binance = BinanceBookTickerStream(symbol=symbol)
        self.dex = PancakeSwapV2Client(rpc_url=rpc_url)
        self.dex_poll_seconds = dex_poll_seconds
        self.stale_after_seconds = stale_after_seconds
        self.dex_latest = None
        self.dex_error: Optional[str] = None
        self.running = False
        self.dex_task = None

    async def start(self):
        if self.running:
            return
        self.running = True
        await self.dex.initialize()
        await self.binance.start()
        self.dex_task = asyncio.create_task(self._poll_dex(), name="pancakeswap-bnbusdt-pool-poller")

    async def stop(self):
        self.running = False
        await self.binance.stop()
        if self.dex_task:
            self.dex_task.cancel()
            try:
                await self.dex_task
            except asyncio.CancelledError:
                pass
            self.dex_task = None
        await self.dex.close()

    async def _poll_dex(self):
        while self.running:
            try:
                self.dex_latest = await self.dex.get_pool_snapshot()
                self.dex_error = None
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.dex_error = str(exc)
            await asyncio.sleep(self.dex_poll_seconds)

    def status(self, now: Optional[float] = None) -> dict:
        now = time.time() if now is None else now
        cex = self.binance.latest
        dex = self.dex_latest
        cex_age = None if cex is None else max(0.0, now - cex.received_at)
        dex_age = None if dex is None else max(0.0, now - dex.received_at)
        return {
            "mode": "PAPER",
            "symbol": self.binance.symbol,
            "binance": {
                "connected_data": cex is not None and cex_age <= self.stale_after_seconds,
                "age_seconds": cex_age,
                "bid": None if cex is None else str(cex.bid_price),
                "ask": None if cex is None else str(cex.ask_price),
                "error": self.binance.last_error,
            },
            "pancakeswap_v2": {
                "connected_data": dex is not None and dex_age <= self.stale_after_seconds,
                "age_seconds": dex_age,
                "pair_address": None if dex is None else dex.pair_address,
                "reserve0": None if dex is None else str(dex.reserve0),
                "reserve1": None if dex is None else str(dex.reserve1),
                "fee_bps": None if dex is None else dex.fee_bps,
                "error": self.dex_error,
            },
            "wallet_connected": False,
            "orders_enabled": False,
            "transactions_enabled": False,
        }
