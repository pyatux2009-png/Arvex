import logging
import math
from typing import Optional, Dict, Any
from app.config import (
    MAX_TRADE_SIZE_USD,
    MAX_DAILY_LOSS_USD,
    MIN_NET_PROFIT_USD,
    MIN_NET_PROFIT_PCT,
    MAX_SLIPPAGE_PCT,
    BOOK_MAX_AGE_SECONDS,
)

logger = logging.getLogger("SafetyEngine")


class SafetyEngine:
    def __init__(
        self,
        max_position_usd: float = MAX_TRADE_SIZE_USD,
        max_daily_loss: Optional[float] = None,
        max_daily_loss_usd: float = MAX_DAILY_LOSS_USD,
        max_single_trade_loss_usd: float = 5.0,
        max_slippage_pct: float = MAX_SLIPPAGE_PCT,
        min_expected_net_profit_usd: float = MIN_NET_PROFIT_USD,
        min_expected_net_profit_pct: float = MIN_NET_PROFIT_PCT,
        max_allowed_book_age_seconds: float = BOOK_MAX_AGE_SECONDS,
        emergency_stop: bool = False,
        **kwargs,
    ):
        self.max_position_usd = float(max_position_usd)
        self.max_daily_loss_usd = float(max_daily_loss if max_daily_loss is not None else max_daily_loss_usd)
        self.max_daily_loss = self.max_daily_loss_usd
        self.max_single_trade_loss_usd = float(max_single_trade_loss_usd)
        self.max_slippage_pct = float(max_slippage_pct)
        self.min_expected_net_profit_usd = float(min_expected_net_profit_usd)
        self.min_expected_net_profit_pct = float(min_expected_net_profit_pct)
        self.max_allowed_book_age_seconds = float(max_allowed_book_age_seconds)
        self.emergency_stop = bool(emergency_stop)
        self.current_daily_loss = 0.0

    def record_loss(self, loss_usd: float):
        loss = float(loss_usd)
        if math.isfinite(loss) and loss > 0:
            self.current_daily_loss += loss

    def reset_daily_loss(self):
        self.current_daily_loss = 0.0

    @staticmethod
    def _number(opportunity: dict, key: str, default: float = 0.0) -> float:
        try:
            value = float(opportunity.get(key, default))
        except (TypeError, ValueError):
            raise ValueError(f"{key} must be numeric")
        if not math.isfinite(value):
            raise ValueError(f"{key} must be finite")
        return value

    def validate_opportunity(self, opportunity: dict) -> Dict[str, Any]:
        if self.emergency_stop or self.current_daily_loss >= self.max_daily_loss_usd:
            return {"allowed": False, "passed": False, "reason": "Emergency stop active or max daily loss limit reached."}

        if str(opportunity.get("risk_level", "")).upper() == "BLOCKED":
            return {"allowed": False, "passed": False, "reason": "Opportunity risk level is BLOCKED."}

        try:
            net_profit_pct = self._number(opportunity, "net_profit_pct")
            net_profit_usd = self._number(opportunity, "net_profit_usd")
            slippage_pct = self._number(opportunity, "slippage_pct")
            quantity = self._number(opportunity, "quantity")
            buy_price = self._number(opportunity, "buy_price")
            book_age = self._number(opportunity, "book_age")
            position_size = quantity * buy_price
        except ValueError as exc:
            return {"allowed": False, "passed": False, "reason": f"Invalid opportunity data: {exc}."}

        if quantity <= 0 or buy_price <= 0 or position_size <= 0:
            return {"allowed": False, "passed": False, "reason": "Quantity, buy price, and position size must be positive."}

        if opportunity.get("liquidity_ok") is not True:
            return {"allowed": False, "passed": False, "reason": "Insufficient or unconfirmed liquidity in order book depth."}

        if position_size > self.max_position_usd:
            return {"allowed": False, "passed": False, "reason": f"Position size {position_size} exceeds max_position_usd {self.max_position_usd}"}

        if net_profit_pct < self.min_expected_net_profit_pct:
            return {"allowed": False, "passed": False, "reason": f"Net profit pct {net_profit_pct}% is below minimum threshold {self.min_expected_net_profit_pct}%"}

        if net_profit_usd < self.min_expected_net_profit_usd:
            return {"allowed": False, "passed": False, "reason": f"Net profit USD {net_profit_usd} is below minimum threshold {self.min_expected_net_profit_usd}"}

        if slippage_pct < 0 or slippage_pct > self.max_slippage_pct:
            return {"allowed": False, "passed": False, "reason": f"Slippage {slippage_pct}% is outside the allowed range 0–{self.max_slippage_pct}%"}

        if book_age < 0 or book_age > self.max_allowed_book_age_seconds:
            return {"allowed": False, "passed": False, "reason": f"Order book is stale or has an invalid age. Age: {book_age}s"}

        return {"allowed": True, "passed": True, "reason": "OK"}
