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
    @staticmethod
    def subscription_batches(symbols, max_args=10):
        """Bybit public Spot accepts at most 10 topic args per subscribe request."""
        if max_args < 1:
            raise ValueError("max_args must be positive")
        topics = [f"orderbook.50.{str(symbol).upper()}" for symbol in symbols]
        return [topics[index:index + max_args] for index in range(0, len(topics), max_args)]

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
            # Bybit Spot limits each subscribe request to 10 topics.
            # Send sequential batches so the expanded 24-symbol universe is fully subscribed.
            for batch in self.subscription_batches(self.symbols, max_args=10):
                await ws.send(json.dumps({"op": "subscribe", "args": batch}))
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



class OkxOrderBookStream(OrderBookStream):
    """OKX books5 publishes complete top-five snapshots, so each update replaces the book."""

    async def _connect(self):
        inst_to_symbol = {f"{symbol[:-4]}-USDT": symbol for symbol in self.symbols if symbol.endswith("USDT")}
        args = [{"channel": "books5", "instId": inst_id} for inst_id in inst_to_symbol]
        for symbol in self.symbols:
            self.exchange.orderbooks.pop(symbol, None)
        async with websockets.connect(
            "wss://ws.okx.com:8443/ws/v5/public",
            ping_interval=20,
            ping_timeout=20,
        ) as ws:
            await ws.send(json.dumps({"op": "subscribe", "args": args}))
            async for raw in ws:
                if not self.running:
                    break
                message = json.loads(raw)
                arg = message.get("arg") or {}
                inst_id = arg.get("instId")
                symbol = inst_to_symbol.get(inst_id)
                rows = message.get("data") or []
                if not symbol or not rows:
                    continue
                row = rows[0]
                bids = [[float(level[0]), float(level[1])] for level in row.get("bids", []) if float(level[1]) > 0]
                asks = [[float(level[0]), float(level[1])] for level in row.get("asks", []) if float(level[1]) > 0]
                if not bids or not asks:
                    continue
                self.exchange.orderbooks[symbol] = {
                    "symbol": symbol, "bids": bids, "asks": asks,
                    "timestamp": time.time(), "source": "websocket",
                    "sequence": row.get("seqId"),
                }


class KrakenOrderBookStream(OrderBookStream):
    """Kraken WS v2 book channel: snapshot first, then merge price-level updates."""

    @staticmethod
    def _merge(levels, updates, reverse=False, snapshot=False):
        book = {} if snapshot else {float(level[0]): float(level[1]) for level in levels}
        for level in updates or []:
            try:
                price = float(level["price"])
                qty = float(level.get("qty", 0.0))
            except (KeyError, TypeError, ValueError):
                continue
            if price <= 0:
                continue
            if qty <= 0:
                book.pop(price, None)
            else:
                book[price] = qty
        return [[price, qty] for price, qty in sorted(book.items(), key=lambda item: item[0], reverse=reverse)[:50]]

    async def _connect(self):
        symbol_to_pair = {}
        pair_to_symbol = {}
        for symbol in self.symbols:
            if not symbol.endswith("USDT"):
                continue
            base = symbol[:-4]
            pair = f"{base}/USDT"
            symbol_to_pair[symbol] = pair
            pair_to_symbol[pair] = symbol
            if base == "BTC":
                pair_to_symbol["XBT/USDT"] = symbol
        self.books = {}
        for symbol in self.symbols:
            self.exchange.orderbooks.pop(symbol, None)
        async with websockets.connect(
            "wss://ws.kraken.com/v2",
            ping_interval=20,
            ping_timeout=20,
        ) as ws:
            await ws.send(json.dumps({
                "method": "subscribe",
                "params": {"channel": "book", "symbol": list(symbol_to_pair.values()), "depth": 10},
                "req_id": 1,
            }))
            async for raw in ws:
                if not self.running:
                    break
                message = json.loads(raw)
                if message.get("channel") != "book":
                    continue
                kind = message.get("type")
                for row in message.get("data") or []:
                    pair = str(row.get("symbol", ""))
                    symbol = pair_to_symbol.get(pair)
                    if not symbol:
                        continue
                    if kind == "snapshot":
                        bids = self._merge([], row.get("bids"), reverse=True, snapshot=True)
                        asks = self._merge([], row.get("asks"), reverse=False, snapshot=True)
                    elif kind == "update":
                        old = self.books.get(symbol)
                        if old is None:
                            continue
                        bids = self._merge(old["bids"], row.get("bids"), reverse=True)
                        asks = self._merge(old["asks"], row.get("asks"), reverse=False)
                    else:
                        continue
                    if not bids or not asks or bids[0][0] >= asks[0][0]:
                        self.books.pop(symbol, None)
                        self.exchange.orderbooks.pop(symbol, None)
                        continue
                    self.books[symbol] = {"bids": bids, "asks": asks}
                    self.exchange.orderbooks[symbol] = {
                        "symbol": symbol, "bids": bids, "asks": asks,
                        "timestamp": time.time(), "source": "websocket",
                    }
