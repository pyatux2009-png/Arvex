import time
import logging
from app.arbitrage.profitability import calculate_net_profit
from app.arbitrage.scoring import evaluate_risk_level
from app.config import BOOK_MAX_AGE_SECONDS
from app.marketdata.provider import MarketDataProvider

logger = logging.getLogger("MarketScanner")


class MarketScanner(MarketDataProvider):
    def __init__(self, exchanges, max_book_age_seconds=BOOK_MAX_AGE_SECONDS):
        self.exchanges = exchanges
        self.max_book_age_seconds = max_book_age_seconds
        self.diagnostics_by_symbol = {}

    async def get_order_book(self, symbol):
        books = {}
        for name, exchange in self.exchanges.items():
            try:
                books[name] = await exchange.get_order_book(symbol)
            except Exception as exc:
                logger.warning("%s book for %s: %s", name, symbol, exc)
        return books

    @staticmethod
    def calculate_vwap_and_depth(side, target_capital_usd):
        if target_capital_usd <= 0:
            return 0.0, 0.0, False
        remaining = target_capital_usd
        qty = spent = 0.0
        for price, amount in side:
            price, amount = float(price), float(amount)
            if price <= 0 or amount <= 0:
                continue
            take = min(amount, remaining / price)
            qty += take
            spent += take * price
            remaining -= take * price
            if remaining <= 1e-9:
                break
        return (spent / qty if qty else 0.0), qty, remaining <= 1e-6

    @staticmethod
    def _vwap_for_qty(side, target_qty):
        remaining = target_qty
        qty = spent = 0.0
        for price, amount in side:
            price, amount = float(price), float(amount)
            take = min(amount, remaining)
            qty += take
            spent += take * price
            remaining -= take
            if remaining <= 1e-12:
                break
        return (spent / qty if qty else 0.0), qty, remaining <= 1e-12

    async def scan_opportunities(self, symbol, target_capital_usd=50.0):
        now = time.time()
        books = {}
        stale_books = []
        errors = []
        for name, exchange in self.exchanges.items():
            try:
                order_book = await exchange.get_order_book(symbol)
                age = max(0.0, now - float(order_book.get("timestamp", 0.0)))
                if age > self.max_book_age_seconds or not order_book.get("bids") or not order_book.get("asks"):
                    stale_books.append(name)
                    continue
                books[name] = (order_book, age)
            except Exception as exc:
                errors.append(name)
                logger.warning("%s scan for %s failed: %s", name, symbol, exc)

        diagnostic = {
            "symbol": symbol, "updated_at": now, "exchanges_configured": len(self.exchanges),
            "books_available": len(books), "stale_or_empty_exchanges": stale_books,
            "exchange_errors": errors, "evaluated_routes": 0, "gross_positive_routes": 0,
            "positive_opportunities": 0, "max_gross_profit_pct": 0.0,
            "max_net_profit_pct": 0.0, "status": "ready" if len(books) >= 2 else "waiting_for_books",
        }
        out = []
        names = list(books)
        for buy in names:
            for sell in names:
                if buy == sell:
                    continue
                diagnostic["evaluated_routes"] += 1
                buy_entry, buy_age = books[buy]
                sell_entry, sell_age = books[sell]
                buy_vwap, max_buy, _ = self.calculate_vwap_and_depth(buy_entry["asks"], target_capital_usd)
                sell_vwap, max_sell, _ = self.calculate_vwap_and_depth(sell_entry["bids"], target_capital_usd)
                qty = min(max_buy, max_sell, target_capital_usd / buy_vwap if buy_vwap else 0.0)
                if qty <= 0:
                    continue
                buy_vwap, _, buy_ok = self._vwap_for_qty(buy_entry["asks"], qty)
                sell_vwap, _, sell_ok = self._vwap_for_qty(sell_entry["bids"], qty)
                metrics = calculate_net_profit(
                    buy_exchange=buy, sell_exchange=sell, buy_price=buy_vwap,
                    sell_price=sell_vwap, volume=qty
                )
                if diagnostic["evaluated_routes"] == 1:
                    diagnostic["max_gross_profit_pct"] = metrics["gross_profit_pct"]
                    diagnostic["max_net_profit_pct"] = metrics["net_profit_pct"]
                else:
                    diagnostic["max_gross_profit_pct"] = max(diagnostic["max_gross_profit_pct"], metrics["gross_profit_pct"])
                    diagnostic["max_net_profit_pct"] = max(diagnostic["max_net_profit_pct"], metrics["net_profit_pct"])
                if metrics["gross_profit_pct"] > 0:
                    diagnostic["gross_positive_routes"] += 1
                risk = evaluate_risk_level(metrics["net_profit_pct"], max(buy_age, sell_age), qty * min(buy_vwap, sell_vwap))
                out.append({
                    "symbol": symbol, "buy_exchange": buy, "sell_exchange": sell,
                    "buy_price": buy_vwap, "sell_price": sell_vwap, "quantity": qty,
                    "position_size": qty * buy_vwap, "liquidity_ok": buy_ok and sell_ok,
                    "book_age": max(buy_age, sell_age), "risk_level": risk, **metrics, "timestamp": now,
                })
        positive = [item for item in out if item["net_profit_usd"] > 0]
        diagnostic["positive_opportunities"] = len(positive)
        self.diagnostics_by_symbol[symbol] = diagnostic
        return sorted(positive, key=lambda item: item["net_profit_usd"], reverse=True)
