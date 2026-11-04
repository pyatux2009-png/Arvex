import asyncio
import json
import logging
import time
from decimal import Decimal, InvalidOperation
from typing import Optional

import websockets

from app.cex_dex.models import TopOfBook

logger = logging.getLogger(__name__)


class BinanceBookTickerStream:
    """Public Binance bookTicker stream. It never creates or signs orders."""

    def __init__(self, symbol: str = "BNBUSDT", url: str = "wss://stream.binance.com:9443/ws/bnbusdt@bookTicker"):
        self.symbol = symbol.upper()
        self.url = url
        self.latest: Optional[TopOfBook] = None
        self.running = False
        self.task = None
        self.last_error: Optional[str] = None

    @staticmethod
    def parse_message(payload: dict, received_at: Optional[float] = None) -> TopOfBook:
        try:
            symbol = str(payload["s"]).upper()
            bid = Decimal(str(payload["b"]))
            bid_qty = Decimal(str(payload["B"]))
            ask = Decimal(str(payload["a"]))
            ask_qty = Decimal(str(payload["A"]))
            update_id = int(payload["u"]) if payload.get("u") is not None else None
        except (KeyError, TypeError, ValueError, InvalidOperation) as exc:
            raise ValueError("invalid Binance bookTicker payload") from exc
        return TopOfBook(
            symbol=symbol,
            bid_price=bid,
            bid_qty=bid_qty,
            ask_price=ask,
            ask_qty=ask_qty,
            received_at=time.time() if received_at is None else received_at,
            update_id=update_id,
        )

    async def start(self):
        if self.running:
            return
        self.running = True
        self.task = asyncio.create_task(self._run(), name="binance-bnbusdt-bookticker")

    async def stop(self):
        self.running = False
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
            self.task = None

    async def _run(self):
        delay = 1.0
        while self.running:
            try:
                async with websockets.connect(self.url, ping_interval=20, ping_timeout=20, close_timeout=5) as ws:
                    delay = 1.0
                    async for raw in ws:
                        if not self.running:
                            break
                        message = json.loads(raw)
                        book = self.parse_message(message)
                        if book.symbol != self.symbol:
                            continue
                        self.latest = book
                        self.last_error = None
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.last_error = str(exc)
                logger.warning("Binance bookTicker disconnected: %s", exc)
                if self.running:
                    await asyncio.sleep(delay)
                    delay = min(delay * 2, 30.0)

