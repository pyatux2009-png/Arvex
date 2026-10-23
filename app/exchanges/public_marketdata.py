"""Public REST order-book adapters used for discovery only.

These adapters deliberately do not implement trading. Live order execution remains
restricted to the Binance and Bybit adapters until separate execution support is tested.
"""
import time

from app.exchanges.http import request_json


class PublicMarketDataExchange:
    exchange_id = "unknown"
    cache_ttl_seconds = 0.75
    failure_cooldown_seconds = 15.0

    def __init__(self):
        self.orderbooks = {}
        self._retry_after = {}

    async def get_order_book(self, symbol):
        symbol = str(symbol).upper()
        now = time.time()
        cached = self.orderbooks.get(symbol)
        if cached and now - cached["timestamp"] <= self.cache_ttl_seconds:
            return cached
        if now < self._retry_after.get(symbol, 0.0):
            if cached:
                return cached
            return {"symbol": symbol, "bids": [], "asks": [], "timestamp": 0.0, "source": "unavailable"}
        try:
            book = await self._fetch(symbol)
            if not book["bids"] or not book["asks"]:
                raise ValueError(f"{self.exchange_id} returned an empty order book for {symbol}")
            book.update({"symbol": symbol, "timestamp": time.time(), "source": "rest"})
            self.orderbooks[symbol] = book
            self._retry_after.pop(symbol, None)
            return book
        except Exception:
            self._retry_after[symbol] = time.time() + self.failure_cooldown_seconds
            raise

    async def _fetch(self, symbol):
        raise NotImplementedError


class OkxMarketDataExchange(PublicMarketDataExchange):
    exchange_id = "okx"
    cache_ttl_seconds = 0.75

    async def _fetch(self, symbol):
        if not symbol.endswith("USDT"):
            raise ValueError(f"OKX spot scanner supports USDT quote only: {symbol}")
        inst_id = f"{symbol[:-4]}-USDT"
        payload = await request_json(
            "GET", "https://www.okx.com/api/v5/market/books",
            params={"instId": inst_id, "sz": "50"}, timeout=5.0,
        )
        if payload.get("code") != "0":
            raise ValueError(f"OKX order-book error: {payload.get('msg', 'unknown error')}")
        rows = payload.get("data") or []
        if not rows:
            raise ValueError(f"OKX has no spot book for {inst_id}")
        row = rows[0]
        return {
            "bids": [[float(level[0]), float(level[1])] for level in row.get("bids", [])],
            "asks": [[float(level[0]), float(level[1])] for level in row.get("asks", [])],
        }


class KrakenMarketDataExchange(PublicMarketDataExchange):
    exchange_id = "kraken"
    cache_ttl_seconds = 1.25
    failure_cooldown_seconds = 30.0

    @staticmethod
    def _pair_candidates(symbol):
        if not symbol.endswith("USDT"):
            raise ValueError(f"Kraken spot scanner supports USDT quote only: {symbol}")
        base = symbol[:-4]
        aliases = {"BTC": "XBT", "DOGE": "XDG"}
        kraken_base = aliases.get(base, base)
        # Kraken's public API accepts several aliases depending on the market listing.
        return [f"{kraken_base}USDT", f"{base}USDT"]

    async def _fetch(self, symbol):
        last_error = None
        for pair in self._pair_candidates(symbol):
            payload = await request_json(
                "GET", "https://api.kraken.com/0/public/Depth",
                params={"pair": pair, "count": "50"}, timeout=5.0,
            )
            errors = payload.get("error") or []
            rows = payload.get("result") or {}
            if errors or not rows:
                last_error = ", ".join(str(error) for error in errors) or "no matching pair"
                continue
            row = next(iter(rows.values()))
            return {
                "bids": [[float(level[0]), float(level[1])] for level in row.get("bids", [])],
                "asks": [[float(level[0]), float(level[1])] for level in row.get("asks", [])],
            }
        raise ValueError(f"Kraken has no usable book for {symbol}: {last_error or 'unknown error'}")
