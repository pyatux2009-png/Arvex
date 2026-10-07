from pydantic import BaseModel
from datetime import datetime
from typing import Optional


class HealthCheckResponse(BaseModel):
    status: str
    mode: str
    timestamp: datetime


class OpportunityDTO(BaseModel):
    symbol: str
    buy_exchange: str
    sell_exchange: str
    buy_price: float
    sell_price: float
    quantity: float
    position_size: float
    gross_profit_pct: float
    net_profit_usd: float
    net_profit_pct: float
    risk_level: str
    liquidity_ok: bool
    book_age: float
    timestamp: float


class TradeOrderDTO(BaseModel):
    order_id: Optional[str]
    symbol: str
    exchange: str
    side: str
    price: float
    amount: float
    status: str
    created_at: datetime
