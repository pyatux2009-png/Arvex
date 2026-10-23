import asyncio
import logging
import math
import time
import uuid

logger = logging.getLogger("RecoveryEngine")

TERMINAL = {"FILLED", "PARTIALLY_FILLED", "CANCELED", "REJECTED", "EXPIRED"}


class RecoveryEngine:
    def __init__(self, exchanges=None, max_recovery_time_seconds=5.0):
        self.exchanges = exchanges or {}
        try:
            timeout = float(max_recovery_time_seconds)
        except (TypeError, ValueError):
            timeout = 5.0
        self.max_recovery_time_seconds = max(0.0, timeout) if math.isfinite(timeout) else 5.0

    async def handle_exposure(self, position_id, exchange, symbol, amount, side):
        ex = self.exchanges.get(exchange)
        try:
            amount = float(amount)
        except (TypeError, ValueError):
            amount = float("nan")
        if not ex or not math.isfinite(amount) or amount <= 0:
            return {
                "position_id": position_id,
                "status": "UNRESOLVED",
                "filled_amount": 0.0,
                "realized_pnl": 0.0,
                "reason": "No recovery adapter or invalid amount",
            }

        side = str(side).lower()
        if side not in {"buy", "sell"}:
            return {
                "position_id": position_id,
                "status": "UNRESOLVED",
                "filled_amount": 0.0,
                "realized_pnl": 0.0,
                "reason": "Invalid exposure side",
            }

        symbol = str(symbol).upper()
        close_side = "sell" if side == "buy" else "buy"
        client_order_id = f"recovery_{str(position_id)[:12]}_{uuid.uuid4().hex[:8]}"

        try:
            book = await ex.get_order_book(symbol)
            levels = book.get("bids" if close_side == "sell" else "asks", [])
            if not levels:
                return {
                    "position_id": position_id,
                    "status": "UNRESOLVED",
                    "filled_amount": 0.0,
                    "reason": "No executable recovery liquidity",
                }
            price = float(levels[0][0])
            if not math.isfinite(price) or price <= 0:
                return {
                    "position_id": position_id,
                    "status": "UNRESOLVED",
                    "filled_amount": 0.0,
                    "reason": "Invalid recovery price from order book",
                }
        except Exception as exc:
            logger.warning("Recovery book lookup failed: %s", exc)
            return {
                "position_id": position_id,
                "status": "UNRESOLVED",
                "filled_amount": 0.0,
                "realized_pnl": 0.0,
                "reason": f"Recovery book lookup failed: {exc}",
            }

        # A submission transport error may happen after the exchange accepted the
        # order. Keep the client ID and reconcile it; never blindly submit again.
        try:
            order = await ex.create_order(
                symbol, close_side, amount, price, client_order_id
            )
        except Exception as exc:
            logger.warning("Recovery order submission uncertain: %s", exc)
            order = {
                "client_order_id": client_order_id,
                "status": "UNKNOWN",
                "filled_amount": 0.0,
                "reason": str(exc),
            }

        order = dict(order or {})
        order.setdefault("client_order_id", client_order_id)

        def read_fill(result, fallback=0.0):
            raw = result.get("filled_amount", fallback)
            try:
                fill = float(raw or 0.0)
            except (TypeError, ValueError):
                return None
            if not math.isfinite(fill) or fill < 0 or fill > amount + 1e-9:
                return None
            return min(fill, amount)

        filled = read_fill(order)
        if filled is None:
            return {
                "position_id": position_id,
                "status": "UNRESOLVED",
                "filled_amount": 0.0,
                "reason": "Recovery order returned an invalid filled amount",
                "closing_order": order,
            }

        status = str(order.get("status", "UNKNOWN")).upper()
        deadline = time.monotonic() + self.max_recovery_time_seconds
        while status not in TERMINAL and time.monotonic() < deadline:
            try:
                latest = await ex.get_order_status(
                    symbol,
                    order.get("order_id"),
                    order.get("client_order_id") or client_order_id,
                )
                if isinstance(latest, dict):
                    order = {**order, **latest}
                    order.setdefault("client_order_id", client_order_id)
                    latest_fill = read_fill(order, filled)
                    if latest_fill is None:
                        return {
                            "position_id": position_id,
                            "status": "UNRESOLVED",
                            "filled_amount": filled,
                            "reason": "Recovery status returned an invalid filled amount",
                            "closing_order": order,
                        }
                    filled = max(filled, latest_fill)
                    order["filled_amount"] = filled
                    status = str(order.get("status", "UNKNOWN")).upper()
            except Exception as exc:
                logger.warning("Recovery status check failed: %s", exc)
            if status not in TERMINAL:
                await asyncio.sleep(min(0.15, max(0.0, deadline - time.monotonic())))

        if status not in TERMINAL:
            # Cancellation can race with a fill. Always query status afterwards.
            try:
                await ex.cancel_order(
                    symbol,
                    order.get("order_id"),
                    order.get("client_order_id") or client_order_id,
                )
            except Exception as exc:
                logger.warning("Recovery cancellation uncertain: %s", exc)
            try:
                latest = await ex.get_order_status(
                    symbol,
                    order.get("order_id"),
                    order.get("client_order_id") or client_order_id,
                )
                if isinstance(latest, dict):
                    order = {**order, **latest}
                    order.setdefault("client_order_id", client_order_id)
                    latest_fill = read_fill(order, filled)
                    if latest_fill is None:
                        return {
                            "position_id": position_id,
                            "status": "UNRESOLVED",
                            "filled_amount": filled,
                            "reason": "Recovery final status returned an invalid filled amount",
                            "closing_order": order,
                        }
                    filled = max(filled, latest_fill)
                    order["filled_amount"] = filled
                    status = str(order.get("status", "UNKNOWN")).upper()
            except Exception as exc:
                logger.warning("Recovery final status check failed: %s", exc)

        if filled >= amount - 1e-9 and status in TERMINAL:
            return {
                "position_id": position_id,
                "status": "RECOVERED",
                "filled_amount": filled,
                "closing_order": order,
            }
        if filled > 0 and status in TERMINAL:
            return {
                "position_id": position_id,
                "status": "PARTIAL_RECOVERY",
                "filled_amount": filled,
                "remaining_amount": max(0.0, amount - filled),
                "closing_order": order,
                "reason": f"Recovery order ended with status {status}; remaining exposure requires reconciliation.",
            }
        return {
            "position_id": position_id,
            "status": "UNRESOLVED" if status not in TERMINAL else "FAILED",
            "filled_amount": filled,
            "reason": f"Recovery status: {status}",
            "closing_order": order,
        }

    async def handle_single_leg_exposure(
        self,
        position_id="legacy",
        exchange=None,
        symbol="",
        amount=0.0,
        side="buy",
        success_exchange=None,
        bought_price=None,
        exchanges=None,
    ):
        if exchanges is not None:
            self.exchanges = exchanges
        return await self.handle_exposure(
            position_id, exchange or success_exchange, symbol, amount, side
        )
