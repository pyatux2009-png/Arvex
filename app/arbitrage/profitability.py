import logging
from typing import Optional
from app.config import EXCHANGE_FEES, OTHER_COSTS_USD

logger = logging.getLogger("ProfitabilityEngine")

def calculate_net_profit(
    buy_exchange: str = "binance",
    sell_exchange: str = "bybit",
    buy_price: float = 0.0,
    sell_price: float = 0.0,
    volume: float = 0.0,
    market_type: str = "taker",
    custom_buy_fee: Optional[float] = None,
    custom_sell_fee: Optional[float] = None,
    slippage_pct: float = 0.05,
    other_costs_usd: float = OTHER_COSTS_USD,
    **kwargs
) -> dict:
    actual_buy_exchange = buy_exchange if isinstance(buy_exchange, str) else "binance"
    actual_sell_exchange = sell_exchange if isinstance(sell_exchange, str) else "bybit"
    
    if isinstance(buy_exchange, (int, float)):
        actual_buy_price = float(buy_exchange)
        actual_sell_price = float(sell_price if sell_price is not None else 0.0)
        actual_volume = float(buy_price if volume == 0.0 else volume)
    else:
        actual_buy_price = float(buy_price)
        actual_sell_price = float(sell_price)
        actual_volume = float(volume)

    if actual_buy_price <= 0 or actual_sell_price <= 0 or actual_volume <= 0:
        return {
            "gross_profit_usd": 0.0,
            "gross_profit_pct": 0.0,
            "buy_fee": 0.0,
            "sell_fee": 0.0,
            "buy_fee_usd": 0.0,
            "sell_fee_usd": 0.0,
            "total_fees_usd": 0.0,
            "fees_pct": 0.0,
            "slippage_usd": 0.0,
            "slippage_pct": 0.0,
            "other_costs_usd": 0.0,
            "net_profit_usd": 0.0,
            "net_profit_pct": 0.0
        }

    if custom_buy_fee is not None:
        buy_fee_rate = float(custom_buy_fee)
    else:
        try:
            buy_fee_rate = float(EXCHANGE_FEES[actual_buy_exchange][market_type])
        except KeyError as exc:
            raise ValueError(f"No configured {market_type} fee for buy exchange: {actual_buy_exchange}") from exc

    if custom_sell_fee is not None:
        sell_fee_rate = float(custom_sell_fee)
    else:
        try:
            sell_fee_rate = float(EXCHANGE_FEES[actual_sell_exchange][market_type])
        except KeyError as exc:
            raise ValueError(f"No configured {market_type} fee for sell exchange: {actual_sell_exchange}") from exc

    gross_buy_cost = actual_buy_price * actual_volume
    gross_sell_revenue = actual_sell_price * actual_volume
    gross_profit_usd = gross_sell_revenue - gross_buy_cost
    gross_profit_pct = ((actual_sell_price - actual_buy_price) / actual_buy_price) * 100.0

    buy_fee_usd = gross_buy_cost * buy_fee_rate
    sell_fee_usd = gross_sell_revenue * sell_fee_rate
    total_fees_usd = buy_fee_usd + sell_fee_usd
    fees_pct = (buy_fee_rate + sell_fee_rate) * 100.0

    # slippage_pct is percentage (e.g., 0.01 = 0.01%, 0.5 = 0.5%)
    slippage_rate = slippage_pct / 100.0
    slippage_usd = gross_buy_cost * slippage_rate

    other_costs = float(other_costs_usd)
    other_costs_pct = (other_costs / gross_buy_cost) * 100.0 if gross_buy_cost > 0 else 0.0

    net_profit_usd = gross_profit_usd - total_fees_usd - slippage_usd - other_costs
    net_profit_pct = gross_profit_pct - fees_pct - slippage_pct - other_costs_pct

    return {
        "gross_profit_usd": round(gross_profit_usd, 4),
        "gross_profit_pct": round(gross_profit_pct, 4),
        "buy_fee": buy_fee_rate,
        "sell_fee": sell_fee_rate,
        "buy_fee_usd": round(buy_fee_usd, 4),
        "sell_fee_usd": round(sell_fee_usd, 4),
        "total_fees_usd": round(total_fees_usd, 4),
        "fees_pct": round(fees_pct, 4),
        "slippage_usd": round(slippage_usd, 4),
        "slippage_pct": round(slippage_pct, 4),
        "other_costs_usd": round(other_costs, 4),
        "net_profit_usd": round(net_profit_usd, 4),
        "net_profit_pct": round(net_profit_pct, 4)
    }