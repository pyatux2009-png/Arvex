import logging
from typing import Dict, Any
from app.trading.orders import OrderManager
from app.trading.positions import PositionManager
from app.recovery.engine import RecoveryEngine
from app.safety.engine import SafetyEngine
from app.portfolio.inventory import InventoryManager
from app.arbitrage.profitability import calculate_net_profit, calculate_realized_profit
from app.config import LIVE_TRADING, EXCHANGE_FEES, MAX_TRADE_SIZE_USD
import math
import os

logger = logging.getLogger("TradeExecutor")


class TradeExecutor:
    def __init__(self, exchanges: Dict[str, Any], mode: str = "PAPER"):
        self.exchanges = exchanges
        self.mode = mode
        self.order_manager = OrderManager(exchanges)
        self.position_manager = PositionManager()
        self.recovery_engine = RecoveryEngine(exchanges)
        self.safety_engine = SafetyEngine()
        self.inventory = InventoryManager()

    @staticmethod
    def _assets(symbol: str):
        symbol = symbol.upper()
        if symbol.endswith("USDT"):
            return symbol[:-4], "USDT"
        return symbol, None

    async def _preflight_balances(self, opportunity: dict) -> dict:
        symbol = opportunity["symbol"]
        base, quote = self._assets(symbol)
        if not quote or quote != "USDT":
            return {"allowed": False, "reason": "Only USDT-quoted spot symbols are supported for execution."}
        amount = float(opportunity["quantity"])
        buy_price = float(opportunity["buy_price"])
        if not all(math.isfinite(value) for value in (amount, buy_price)) or amount <= 0 or buy_price <= 0:
            return {"allowed": False, "reason": "Quantity and buy price must be finite positive numbers."}
        buy_cost = amount * buy_price
        buy_fee_rate = EXCHANGE_FEES.get(opportunity["buy_exchange"], {}).get("taker")
        if buy_fee_rate is None:
            return {"allowed": False, "reason": "No configured taker fee for buy exchange."}
        buy_fee = buy_cost * buy_fee_rate
        sell_ex = self.exchanges[opportunity["sell_exchange"]]
        buy_ex = self.exchanges[opportunity["buy_exchange"]]
        if buy_cost > MAX_TRADE_SIZE_USD + 1e-9:
            return {"allowed": False, "reason": f"Trade size exceeds configured maximum of ${MAX_TRADE_SIZE_USD:.2f}."}
        buy_bal = await buy_ex.get_balance()
        sell_bal = await sell_ex.get_balance()
        if quote and float(buy_bal.get(quote, 0.0)) + 1e-9 < buy_cost + buy_fee:
            return {"allowed": False, "reason": f"Insufficient {quote} balance on {opportunity['buy_exchange']}"}
        if float(sell_bal.get(base, 0.0)) + 1e-9 < amount:
            return {"allowed": False, "reason": f"Insufficient {base} inventory on {opportunity['sell_exchange']}"}
        return {"allowed": True, "reason": "OK"}

    async def execute_arbitrage(self, opportunity: dict) -> dict:
        if not isinstance(opportunity, dict):
            return {"status": "BLOCKED", "reason": "Opportunity must be an object."}
        if LIVE_TRADING and self.mode == "LIVE":
            if not os.getenv("LIVE_API_TOKEN", "").strip():
                return {"status": "BLOCKED", "reason": "LIVE_API_TOKEN is required before any LIVE order can be submitted."}
            for ex_name in (opportunity.get("buy_exchange"), opportunity.get("sell_exchange")):
                ex = self.exchanges.get(ex_name)
                if not ex or getattr(ex, "paper_mode", True) or not getattr(ex, "api_key", None):
                    return {"status": "BLOCKED", "reason": f"LIVE trading requires valid API credentials for {ex_name}."}

        symbol = str(opportunity.get("symbol", "")).upper()
        buy_exchange = str(opportunity.get("buy_exchange", "")).lower()
        sell_exchange = str(opportunity.get("sell_exchange", "")).lower()
        if not symbol.endswith("USDT") or symbol == "USDT":
            return {"status": "BLOCKED", "reason": "Only USDT-quoted spot symbols are supported."}
        if buy_exchange == sell_exchange or buy_exchange not in self.exchanges or sell_exchange not in self.exchanges:
            return {"status": "BLOCKED", "reason": "Route must use two distinct execution-enabled exchanges."}
        if opportunity.get("execution_supported") is False:
            return {"status": "BLOCKED", "reason": "This route is discovery-only and cannot be executed."}
        try:
            sell_price_check = float(opportunity.get("sell_price"))
            expected_net = float(opportunity.get("net_profit_usd"))
            if not math.isfinite(sell_price_check) or sell_price_check <= 0:
                raise ValueError("sell_price must be finite and positive")
            if not math.isfinite(expected_net) or expected_net <= 0:
                raise ValueError("net_profit_usd must be finite and positive")
        except (TypeError, ValueError) as exc:
            return {"status": "BLOCKED", "reason": f"Invalid trade economics: {exc}"}
        safety_check = self.safety_engine.validate_opportunity(opportunity)
        if not safety_check.get("allowed", False):
            return {"status": "BLOCKED", "reason": f"Safety check failed: {safety_check.get('reason')}"}

        try:
            balance_check = await self._preflight_balances(opportunity)
        except Exception as exc:
            return {"status": "BLOCKED", "reason": f"Balance preflight failed: {exc}"}
        if not balance_check["allowed"]:
            return {"status": "BLOCKED", "reason": balance_check["reason"]}

        symbol = opportunity["symbol"]
        buy_ex = opportunity["buy_exchange"]
        sell_ex = opportunity["sell_exchange"]
        quantity = float(opportunity["quantity"])
        buy_price = float(opportunity["buy_price"])
        sell_price = float(opportunity["sell_price"])
        position_id = self.position_manager.create_position(symbol, buy_ex, sell_ex, quantity)

        buy_order_res = await self.order_manager.create_order(buy_ex, symbol, "buy", quantity, buy_price)
        buy_status = buy_order_res.get("status", "UNKNOWN")
        bought_filled = float(buy_order_res.get("filled_amount", 0.0) or 0.0)
        if buy_status in {"UNKNOWN", "SUBMITTED", "NEW"}:
            checked_buy = await self.order_manager.resolve_order(buy_ex, symbol, buy_order_res)
            buy_order_res = {**buy_order_res, **checked_buy}
            buy_status = str(buy_order_res.get("status", "UNKNOWN")).upper()
            bought_filled = float(buy_order_res.get("filled_amount", 0.0) or 0.0)
        if buy_status in {"UNKNOWN", "SUBMITTED", "NEW"}:
            self.position_manager.set_position_status(position_id, "UNRESOLVED")
            return {
                "status": "UNRESOLVED",
                "reason": "Buy order remains unconfirmed after status checks and cancellation attempt; no second order was submitted.",
                "buy_order": buy_order_res,
            }
        # A canceled/expired IOC order can still have a confirmed partial fill.
        # Process that filled quantity rather than discarding the resulting exposure.
        if buy_status == "REJECTED" or bought_filled <= 0:
            self.position_manager.set_position_status(position_id, buy_status)
            return {"status": "FAILED", "reason": f"Buy order has no confirmed fill (status {buy_status})", "buy_order": buy_order_res}

        self.position_manager.update_leg_fill(position_id, "buy", bought_filled, buy_order_res.get("avg_price", buy_price))
        sell_order_res = await self.order_manager.create_order(sell_ex, symbol, "sell", bought_filled, sell_price)
        sell_status = sell_order_res.get("status", "UNKNOWN")
        sold_filled = float(sell_order_res.get("filled_amount", 0.0) or 0.0)
        if sell_status in {"UNKNOWN", "SUBMITTED", "NEW"}:
            checked_sell = await self.order_manager.resolve_order(sell_ex, symbol, sell_order_res)
            sell_order_res = {**sell_order_res, **checked_sell}
            sell_status = str(sell_order_res.get("status", "UNKNOWN")).upper()
            sold_filled = float(sell_order_res.get("filled_amount", 0.0) or 0.0)
        if sell_status in {"UNKNOWN", "SUBMITTED", "NEW"}:
            self.position_manager.set_position_status(position_id, "UNRESOLVED")
            # Do not place a recovery order while the original sell might still fill.
            # That could oversell inventory if the exchange later confirms execution.
            return {
                "status": "UNRESOLVED",
                "reason": "Sell order remains unconfirmed after status checks and cancellation attempt; exposure requires manual reconciliation.",
                "sell_order": sell_order_res,
                "buy_order": buy_order_res,
            }

        self.position_manager.update_leg_fill(position_id, "sell", sold_filled, sell_order_res.get("avg_price", sell_price))
        if sold_filled < bought_filled:
            self.position_manager.set_position_status(position_id, "PARTIALLY_FILLED")
            recovery_result = await self.recovery_engine.handle_exposure(position_id, buy_ex, symbol, bought_filled - sold_filled, "buy")
            return {"status": "PARTIAL_RECOVERY", "sold_filled": sold_filled, "recovery": recovery_result}

        realized_buy_fee = buy_order_res.get("fee_usd")
        realized_sell_fee = sell_order_res.get("fee_usd")
        realized_buy_price = float(buy_order_res.get("avg_price", buy_price))
        realized_sell_price = float(sell_order_res.get("avg_price", sell_price))
        other_costs = float(opportunity.get("other_costs_usd", 0.0))
        if realized_buy_fee is not None and realized_sell_fee is not None:
            # PAPER adapters report the fees actually deducted from each fill.
            # Use those values rather than re-estimating from a configured rate.
            pnl_calc = calculate_realized_profit(
                buy_price=realized_buy_price,
                sell_price=realized_sell_price,
                volume=sold_filled,
                buy_fee_usd=float(realized_buy_fee),
                sell_fee_usd=float(realized_sell_fee),
                other_costs_usd=other_costs,
            )
        else:
            # Some LIVE exchange responses do not include execution fees. Until
            # fee history is confirmed, label this as an estimate, not realized.
            pnl_calc = calculate_net_profit(
                buy_exchange=buy_ex,
                sell_exchange=sell_ex,
                buy_price=realized_buy_price,
                sell_price=realized_sell_price,
                volume=sold_filled,
                slippage_pct=0.0,
                other_costs_usd=other_costs,
            )
            pnl_calc["fee_source"] = "configured_estimate"
        net_pnl = pnl_calc["net_profit_usd"]
        if net_pnl < 0:
            self.safety_engine.record_loss(-net_pnl)
        closed_pos = self.position_manager.close_position(position_id, net_pnl)
        return {"status": "FILLED", "net_profit_usd": net_pnl, "profitability": pnl_calc, "position": closed_pos}
