import asyncio
import logging
import math
import time

from app.arbitrage.profitability import calculate_net_profit
from app.arbitrage.scoring import evaluate_risk_level
from app.config import BOOK_MAX_AGE_SECONDS, ESTIMATED_SLIPPAGE_PCT
from app.marketdata.provider import MarketDataProvider

logger = logging.getLogger("MarketScanner")


class MarketScanner(MarketDataProvider):
    """Cross-exchange spot scanner with diagnostics for every rejected route."""

    def __init__(
        self,
        exchanges,
        max_book_age_seconds=BOOK_MAX_AGE_SECONDS,
        estimated_slippage_pct=ESTIMATED_SLIPPAGE_PCT,
        execution_exchanges=None,
    ):
        self.exchanges = exchanges
        self.max_book_age_seconds = max(0.0, float(max_book_age_seconds))
        self.estimated_slippage_pct = max(0.0, float(estimated_slippage_pct))
        self.execution_exchanges = set(execution_exchanges or exchanges.keys())
        self.diagnostics_by_symbol = {}

    async def _fetch_book(self, name, exchange, symbol):
        try:
            book = await exchange.get_order_book(symbol)
            return name, book, None
        except Exception as exc:
            logger.warning("%s book for %s failed: %s", name, symbol, exc)
            return name, None, str(exc)[:240]

    async def get_order_book(self, symbol):
        results = await asyncio.gather(
            *(self._fetch_book(name, exchange, symbol) for name, exchange in self.exchanges.items())
        )
        return {name: book for name, book, error in results if book is not None}

    @staticmethod
    def _clean_side(side, reverse=False):
        cleaned = []
        for level in side or []:
            try:
                price, amount = float(level[0]), float(level[1])
            except (TypeError, ValueError, IndexError):
                continue
            if not math.isfinite(price) or not math.isfinite(amount) or price <= 0 or amount <= 0:
                continue
            cleaned.append([price, amount])
        return sorted(cleaned, key=lambda item: item[0], reverse=reverse)

    @staticmethod
    def calculate_vwap_and_depth(side, target_capital_usd):
        if not math.isfinite(float(target_capital_usd)) or target_capital_usd <= 0:
            return 0.0, 0.0, False
        remaining = float(target_capital_usd)
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
        remaining = float(target_qty)
        qty = spent = 0.0
        for price, amount in side:
            price, amount = float(price), float(amount)
            if price <= 0 or amount <= 0:
                continue
            take = min(amount, remaining)
            qty += take
            spent += take * price
            remaining -= take
            if remaining <= 1e-12:
                break
        return (spent / qty if qty else 0.0), qty, remaining <= 1e-9

    @staticmethod
    def _worst_price_for_qty(side, target_qty):
        """Return the worst price touched to fill target_qty from this book side."""
        remaining = float(target_qty)
        for price, amount in side:
            price, amount = float(price), float(amount)
            if price <= 0 or amount <= 0:
                continue
            take = min(amount, remaining)
            remaining -= take
            if remaining <= 1e-9:
                return price
        return 0.0

    async def scan_opportunities(self, symbol, target_capital_usd=50.0):
        symbol = str(symbol).upper()
        target_capital_usd = float(target_capital_usd)
        started_at = time.time()
        results = await asyncio.gather(
            *(self._fetch_book(name, exchange, symbol) for name, exchange in self.exchanges.items())
        )

        books = {}
        errors = {}
        stale_or_empty = {}
        now = time.time()
        for name, book, error in results:
            if error:
                errors[name] = error
                continue
            try:
                timestamp = float(book.get("timestamp", 0.0))
                age = max(0.0, now - timestamp)
                bids = self._clean_side(book.get("bids"), reverse=True)
                asks = self._clean_side(book.get("asks"), reverse=False)
            except (AttributeError, TypeError, ValueError, OverflowError):
                stale_or_empty[name] = "malformed_book"
                continue
            if not math.isfinite(timestamp) or timestamp <= 0 or age > self.max_book_age_seconds:
                stale_or_empty[name] = "stale_book"
                continue
            if not bids or not asks:
                stale_or_empty[name] = "empty_book"
                continue
            if bids[0][0] >= asks[0][0]:
                stale_or_empty[name] = "crossed_or_invalid_book"
                continue
            books[name] = ({"bids": bids, "asks": asks, "timestamp": timestamp, "source": book.get("source", "unknown")}, age)

        diagnostic = {
            "symbol": symbol,
            "updated_at": now,
            "scan_duration_ms": round((now - started_at) * 1000.0, 2),
            "exchanges_configured": len(self.exchanges),
            "books_available": len(books),
            "stale_or_empty_exchanges": stale_or_empty,
            "exchange_errors": errors,
            "evaluated_routes": 0,
            "gross_positive_routes": 0,
            "positive_opportunities": 0,
            "nonpositive_net_routes": 0,
            "insufficient_liquidity_routes": 0,
            "below_minimum_size_routes": 0,
            "max_gross_profit_pct": None,
            "max_net_profit_pct": None,
            "estimated_slippage_pct": self.estimated_slippage_pct,
            "status": "waiting_for_books" if len(books) < 2 else "no_profitable_routes",
            "best_gross_candidate": None,
        }

        candidates = []
        names = list(books)
        for buy in names:
            for sell in names:
                if buy == sell:
                    continue
                diagnostic["evaluated_routes"] += 1
                buy_book, buy_age = books[buy]
                sell_book, sell_age = books[sell]
                buy_vwap_at_capital, max_buy_qty, buy_depth_full = self.calculate_vwap_and_depth(
                    buy_book["asks"], target_capital_usd
                )
                sell_vwap_at_capital, max_sell_qty, sell_depth_full = self.calculate_vwap_and_depth(
                    sell_book["bids"], target_capital_usd
                )
                if buy_vwap_at_capital <= 0 or sell_vwap_at_capital <= 0:
                    diagnostic["insufficient_liquidity_routes"] += 1
                    continue

                qty = min(max_buy_qty, max_sell_qty, target_capital_usd / buy_vwap_at_capital)
                if not math.isfinite(qty) or qty <= 0:
                    diagnostic["insufficient_liquidity_routes"] += 1
                    continue
                buy_vwap, buy_filled_qty, buy_ok = self._vwap_for_qty(buy_book["asks"], qty)
                sell_vwap, sell_filled_qty, sell_ok = self._vwap_for_qty(sell_book["bids"], qty)
                buy_order_price = self._worst_price_for_qty(buy_book["asks"], qty)
                sell_order_price = self._worst_price_for_qty(sell_book["bids"], qty)
                if buy_vwap <= 0 or sell_vwap <= 0 or buy_order_price <= 0 or sell_order_price <= 0 or buy_filled_qty + 1e-9 < qty or sell_filled_qty + 1e-9 < qty:
                    diagnostic["insufficient_liquidity_routes"] += 1
                    continue

                try:
                    metrics = calculate_net_profit(
                        buy_exchange=buy,
                        sell_exchange=sell,
                        buy_price=buy_vwap,
                        sell_price=sell_vwap,
                        volume=qty,
                        slippage_pct=self.estimated_slippage_pct,
                    )
                except (KeyError, TypeError, ValueError) as exc:
                    errors[f"{buy}->{sell}"] = f"profitability: {exc}"[:240]
                    continue

                gross_pct = metrics["gross_profit_pct"]
                net_pct = metrics["net_profit_pct"]
                diagnostic["max_gross_profit_pct"] = gross_pct if diagnostic["max_gross_profit_pct"] is None else max(diagnostic["max_gross_profit_pct"], gross_pct)
                diagnostic["max_net_profit_pct"] = net_pct if diagnostic["max_net_profit_pct"] is None else max(diagnostic["max_net_profit_pct"], net_pct)
                if gross_pct > 0:
                    diagnostic["gross_positive_routes"] += 1
                if metrics["net_profit_usd"] <= 0:
                    diagnostic["nonpositive_net_routes"] += 1
                position_size = qty * buy_vwap
                if position_size < min(5.0, target_capital_usd * 0.1):
                    diagnostic["below_minimum_size_routes"] += 1
                    continue

                # The requested capital may exceed visible depth; execution is still valid for the smaller qty selected above.
                # _vwap_for_qty already confirmed both books can fill this exact qty.
                liquidity_ok = bool(buy_filled_qty + 1e-9 >= qty and sell_filled_qty + 1e-9 >= qty)
                item = {
                    "symbol": symbol,
                    "buy_exchange": buy,
                    "sell_exchange": sell,
                    "buy_price": buy_vwap,
                    "sell_price": sell_vwap,
                    "buy_order_price": buy_order_price,
                    "sell_order_price": sell_order_price,
                    "quantity": qty,
                    "position_size": position_size,
                    "liquidity_ok": liquidity_ok,
                    "book_age": max(buy_age, sell_age),
                    "buy_book_source": buy_book.get("source", "unknown"),
                    "sell_book_source": sell_book.get("source", "unknown"),
                    "execution_supported": buy in self.execution_exchanges and sell in self.execution_exchanges,
                    "risk_level": evaluate_risk_level(net_pct, max(buy_age, sell_age), qty * min(buy_vwap, sell_vwap)),
                    **metrics,
                    "timestamp": now,
                }
                candidates.append(item)

        positive = [
            item for item in candidates
            if item["net_profit_usd"] > 0 and item["liquidity_ok"]
        ]
        diagnostic["positive_opportunities"] = len(positive)
        if len(books) < 2:
            diagnostic["status"] = "waiting_for_books"
        elif positive:
            diagnostic["status"] = "opportunities_found"
        elif diagnostic["evaluated_routes"] == 0:
            diagnostic["status"] = "no_routes_evaluated"
        elif diagnostic["gross_positive_routes"] == 0:
            diagnostic["status"] = "no_gross_spread"
        elif diagnostic["nonpositive_net_routes"] > 0:
            diagnostic["status"] = "spread_erased_by_costs"
        else:
            diagnostic["status"] = "liquidity_or_minimum_size"

        gross_candidates = sorted(candidates, key=lambda item: item["gross_profit_pct"], reverse=True)
        if gross_candidates:
            best = gross_candidates[0]
            diagnostic["best_gross_candidate"] = {
                "buy_exchange": best["buy_exchange"],
                "sell_exchange": best["sell_exchange"],
                "gross_profit_pct": best["gross_profit_pct"],
                "net_profit_pct": best["net_profit_pct"],
                "net_profit_usd": best["net_profit_usd"],
                "position_size": best["position_size"],
                "liquidity_ok": best["liquidity_ok"],
                "execution_supported": best["execution_supported"],
            }
        self.diagnostics_by_symbol[symbol] = diagnostic
        return sorted(positive, key=lambda item: item["net_profit_usd"], reverse=True)
