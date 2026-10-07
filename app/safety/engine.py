import logging
from typing import Optional, Dict, Any
from app.config import (
    MAX_TRADE_SIZE_USD,
    MAX_DAILY_LOSS_USD,
    MIN_NET_PROFIT_USD,
    MIN_NET_PROFIT_PCT,
    MAX_SLIPPAGE_PCT,
    BOOK_MAX_AGE_SECONDS
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
        **kwargs
    ):
        self.max_position_usd = max_position_usd
        if max_daily_loss is not None:
            self.max_daily_loss_usd = max_daily_loss
        else:
            self.max_daily_loss_usd = max_daily_loss_usd
        self.max_daily_loss = self.max_daily_loss_usd
        self.max_single_trade_loss_usd = max_single_trade_loss_usd
        self.max_slippage_pct = max_slippage_pct
        self.min_expected_net_profit_usd = min_expected_net_profit_usd
        self.min_expected_net_profit_pct = min_expected_net_profit_pct
        self.max_allowed_book_age_seconds = max_allowed_book_age_seconds
        self.emergency_stop = emergency_stop
        self.current_daily_loss = 0.0

    def record_loss(self, loss_usd: float):
        if loss_usd > 0:
            self.current_daily_loss += float(loss_usd)

    def reset_daily_loss(self):
        self.current_daily_loss = 0.0

    def validate_opportunity(self, opportunity: dict) -> Dict[str, Any]:
        if self.emergency_stop or self.current_daily_loss >= self.max_daily_loss_usd:
            return {"allowed": False, "passed": False, "reason": "Emergency stop active or max daily loss limit reached."}

        if str(opportunity.get("risk_level", "")).upper() == "BLOCKED":
            return {"allowed": False, "passed": False, "reason": "Opportunity risk level is BLOCKED."}

        net_profit_pct = opportunity.get("net_profit_pct", 0.0)
        net_profit_usd = opportunity.get("net_profit_usd", 0.0)
        slippage_pct = opportunity.get("slippage_pct", 0.0)
        quantity = opportunity.get("quantity", 0.0)
        buy_price = opportunity.get("buy_price", 0.0)
        position_size = quantity * buy_price if (quantity > 0 and buy_price > 0) else opportunity.get("position_size", 0.0)
        liquidity_ok = opportunity.get("liquidity_ok", True)
        book_age = opportunity.get("book_age", 0.0)

        if position_size > self.max_position_usd:
            return {"allowed": False, "passed": False, "reason": f"Position size {position_size} exceeds max_position_usd {self.max_position_usd}"}

        if "net_profit_pct" in opportunity and net_profit_pct < self.min_expected_net_profit_pct:
            return {"allowed": False, "passed": False, "reason": f"Net profit pct {net_profit_pct}% is below minimum threshold {self.min_expected_net_profit_pct}%"}

        if "net_profit_usd" in opportunity and net_profit_usd < self.min_expected_net_profit_usd:
            return {"allowed": False, "passed": False, "reason": f"Net profit USD {net_profit_usd} is below minimum threshold {self.min_expected_net_profit_usd}"}

        if slippage_pct > self.max_slippage_pct:
            return {"allowed": False, "passed": False, "reason": f"Slippage {slippage_pct}% exceeds maximum allowed {self.max_slippage_pct}%"}

        if not liquidity_ok:
            return {"allowed": False, "passed": False, "reason": "Insufficient liquidity in order book depth."}

        if book_age > self.max_allowed_book_age_seconds:
            return {"allowed": False, "passed": False, "reason": f"Order book is stale. Age: {book_age}s"}

        return {"allowed": True, "passed": True, "reason": "OK"}