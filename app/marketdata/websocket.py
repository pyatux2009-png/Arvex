import asyncio
import json
import time
import logging

import websockets

logger = logging.getLogger("MarketDataWS")


class OrderBookStream:
    def __init__(self, exchange, symbols):
        self.exchange = exchange
        self.symbols = [symbol.upper() for symbol in symbols]
        self.task = None
        self.running = False

    async def start(self):
        if self.running:
            return
        self.running = True
        self.task = asyncio.create_task(self._run())

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
        while self.running:
            try:
                await self._connect()
                # A clean server-side disconnect must not create a hot reconnect loop.
                if self.running:
                    await asyncio.sleep(1.0)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.warning("%s websocket: %s", self.exchange.__class__.__name__, exc)
                if self.running:
                    await asyncio.sleep(2.0)


class BinanceOrderBookStream(OrderBookStream):
    async def _connect(self):
        streams = "/".join(f"{symbol.lower()}@depth20@100ms" for symbol in self.symbols)
        url = f"wss://stream.binance.com:9443/stream?streams={streams}"
        async with websockets.connect(url, ping_interval=20, ping_timeout=20) as ws:
            async for raw in ws:
                if not self.running:
                    break
                message = json.loads(raw).get("data", {})
                symbol = message.get("s")
                if not symbol:
                    continue
                bids = [[float(price), float(qty)] for price, qty in message.get("b", []) if float(qty) > 0]
                asks = [[float(price), float(qty)] for price, qty in message.get("a", []) if float(qty) > 0]
                if not bids or not asks:
                    continue
                self.exchange.orderbooks[symbol] = {
                    "symbol": symbol,
                    "bids": bids,
                    "asks": asks,
                    "timestamp": time.time(),
                    "source": "websocket",
                }


class BybitOrderBookStream(OrderBookStream):
    def __init__(self, exchange, symbols):
        super().__init__(exchange, symbols)
        self.books = {}
        self.initialized = set()

    @staticmethod
    def _apply(levels, updates, reverse=False):
        book = {float(price): float(qty) for price, qty in levels if float(price) > 0 and float(qty) > 0}
        for price_raw, qty_raw in updates:
            price, qty = float(price_raw), float(qty_raw)
            if price <= 0:
                continue
            if qty <= 0:
                book.pop(price, None)
            else:
                book[price] = qty
        return [
            [price, qty]
            for price, qty in sorted(book.items(), key=lambda item: item[0], reverse=reverse)[:50]
        ]

    async def _connect(self):
        # Never allow an old local book to masquerade as a fresh book after reconnect.
        self.books.clear()
        self.initialized.clear()
        for symbol in self.symbols:
            self.exchange.orderbooks.pop(symbol, None)

        async with websockets.connect(
            "wss://stream.bybit.com/v5/public/spot",
            ping_interval=20,
            ping_timeout=20,
        ) as ws:
            await ws.send(json.dumps({
                "op": "subscribe",
                "args": [f"orderbook.50.{symbol}" for symbol in self.symbols],
            }))
            async for raw in ws:
                if not self.running:
                    break
                message = json.loads(raw)
                topic = message.get("topic", "")
                data = message.get("data", {})
                if not data or not topic:
                    continue

                symbol = topic.rsplit(".", 1)[-1].upper()
                if symbol not in self.symbols:
                    continue

                # Bybit deltas are meaningful only after a complete snapshot. u=1
                # also marks a reset snapshot after a matching-engine restart.
                is_snapshot = message.get("type") == "snapshot" or int(data.get("u", 0) or 0) == 1
                if is_snapshot:
                    bids = self._apply([], data.get("b", []), reverse=True)
                    asks = self._apply([], data.get("a", []), reverse=False)
                    if not bids or not asks:
                        self.books.pop(symbol, None)
                        self.initialized.discard(symbol)
                        self.exchange.orderbooks.pop(symbol, None)
                        continue
                    self.initialized.add(symbol)
                else:
                    if symbol not in self.initialized:
                        continue
                    old = self.books[symbol]
                    bids = self._apply(old["bids"], data.get("b", []), reverse=True)
                    asks = self._apply(old["asks"], data.get("a", []), reverse=False)
                    if not bids or not asks:
                        self.books.pop(symbol, None)
                        self.initialized.discard(symbol)
                        self.exchange.orderbooks.pop(symbol, None)
                        continue

                self.books[symbol] = {"bids": bids, "asks": asks}
                self.exchange.orderbooks[symbol] = {
                    "symbol": symbol,
                    "bids": bids,
                    "asks": asks,
                    "timestamp": time.time(),
                    "source": "websocket",
                    "update_id": data.get("u"),
                    "sequence": data.get("seq"),
                }
