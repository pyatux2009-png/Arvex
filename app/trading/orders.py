import asyncio
import logging
import time
import uuid

logger = logging.getLogger("OrderManager")

# PARTIALLY_FILLED is terminal for an IOC order only when the exchange confirms it.
TERMINAL = {"FILLED", "PARTIALLY_FILLED", "CANCELED", "REJECTED", "EXPIRED"}


class OrderManager:
    def __init__(self, exchanges):
        self.exchanges = exchanges
        self.active_orders = {}

    async def create_order(self, exchange_name, symbol, side, amount, price, client_order_id=None):
        exchange = self.exchanges.get(exchange_name)
        client_id = client_order_id or f"cid_{uuid.uuid4().hex[:16]}"
        if client_id in self.active_orders:
            return self.active_orders[client_id]
        if not exchange:
            return {
                "order_id": None, "client_order_id": client_id, "status": "REJECTED",
                "filled_amount": 0.0, "remaining_amount": amount, "avg_price": 0.0,
                "reason": "Exchange adapter not found",
            }
        try:
            result = await exchange.create_order(symbol, side, amount, price, client_id)
        except Exception as exc:
            # A transport error can happen after the exchange accepted the order.
            # Keep UNKNOWN and resolve by client ID; never retry with a new ID blindly.
            return {
                "order_id": None, "client_order_id": client_id, "status": "UNKNOWN",
                "filled_amount": 0.0, "remaining_amount": amount, "avg_price": 0.0,
                "reason": str(exc),
            }
        filled = float(result.get("filled_amount", 0.0) or 0.0)
        record = {
            **result,
            "exchange": exchange_name,
            "client_order_id": result.get("client_order_id", client_id),
            "requested_amount": amount,
            "filled_amount": filled,
            "remaining_amount": max(0.0, amount - filled),
            "timestamp": result.get("timestamp", time.time()),
        }
        self.active_orders[client_id] = record
        return record

    async def check_order_status_with_timeout(
        self, exchange_name, symbol, order_id, client_order_id, timeout_seconds=3.0
    ):
        exchange = self.exchanges.get(exchange_name)
        if not exchange:
            return {
                "order_id": order_id, "client_order_id": client_order_id,
                "status": "UNKNOWN", "filled_amount": 0.0,
                "reason": "Exchange adapter not found",
            }

        deadline = time.monotonic() + max(0.0, timeout_seconds)
        last = None
        while time.monotonic() < deadline:
            try:
                last = await exchange.get_order_status(symbol, order_id, client_order_id)
                status = str(last.get("status", "UNKNOWN")).upper()
                if status in TERMINAL:
                    return last
            except Exception as exc:
                logger.warning("status check %s failed: %s", exchange_name, exc)
            await asyncio.sleep(0.15)

        return {
            **(last or {}),
            "order_id": order_id,
            "client_order_id": client_order_id,
            "status": "UNKNOWN",
            "timestamp": time.time(),
            "reason": "Timeout waiting for exchange confirmation",
        }

    async def resolve_order(self, exchange_name, symbol, order_result, timeout_seconds=3.0):
        """Resolve NEW/SUBMITTED/UNKNOWN orders; cancel and recheck if still uncertain."""
        status = str(order_result.get("status", "UNKNOWN")).upper()
        if status in TERMINAL:
            return order_result

        order_id = order_result.get("order_id")
        client_order_id = order_result.get("client_order_id")
        resolved = await self.check_order_status_with_timeout(
            exchange_name, symbol, order_id, client_order_id, timeout_seconds
        )
        status = str(resolved.get("status", "UNKNOWN")).upper()
        if status in TERMINAL:
            return resolved

        exchange = self.exchanges.get(exchange_name)
        if exchange is not None:
            try:
                # Cancellation can race with a fill. Always query status again after it.
                await exchange.cancel_order(symbol, order_id, client_order_id)
            except Exception as exc:
                logger.warning("cancel uncertain order %s failed: %s", exchange_name, exc)

        final = await self.check_order_status_with_timeout(
            exchange_name, symbol, order_id, client_order_id, timeout_seconds=1.0
        )
        final_status = str(final.get("status", "UNKNOWN")).upper()
        if final_status in TERMINAL:
            return final
        return {
            **final,
            "order_id": order_id,
            "client_order_id": client_order_id,
            "status": "UNKNOWN",
            "reason": "Order remains unresolved after status checks and cancellation attempt",
        }
