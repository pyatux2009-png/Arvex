import logging
import math
from typing import Optional

from app.config import EXCHANGE_FEES, OTHER_COSTS_USD

logger = logging.getLogger("ProfitabilityEngine")


def _finite_number(value: float, name: str) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{name} must be a finite number")
    return result


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
    **kwargs,
) -> dict:
    # Preserve the legacy positional form calculate_net_profit(buy, sell, qty).
    actual_buy_exchange = buy_exchange if isinstance(buy_exchange, str) else "binance"
    actual_sell_exchange = sell_exchange if isinstance(sell_exchange, str) else "bybit"
    if isinstance(buy_exchange, (int, float)):
        actual_buy_price = _finite_number(buy_exchange, "buy_price")
        # In the legacy three-positional-argument form, sell_exchange carries
        # the numeric sell price and buy_price carries the quantity.
        legacy_sell_price = sell_exchange if isinstance(sell_exchange, (int, float)) else sell_price
        actual_sell_price = _finite_number(legacy_sell_price, "sell_price")
        actual_volume = _finite_number(buy_price if volume == 0.0 else volume, "volume")
    else:
        actual_buy_price = _finite_number(buy_price, "buy_price")
        actual_sell_price = _finite_number(sell_price, "sell_price")
        actual_volume = _finite_number(volume, "volume")

    slippage_pct = _finite_number(slippage_pct, "slippage_pct")
    other_costs = _finite_number(other_costs_usd, "other_costs_usd")
    if slippage_pct < 0:
        raise ValueError("slippage_pct cannot be negative")
    if other_costs < 0:
        raise ValueError("other_costs_usd cannot be negative")

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
            "net_profit_pct": 0.0,
        }

    if custom_buy_fee is not None:
        buy_fee_rate = _finite_number(custom_buy_fee, "custom_buy_fee")
    else:
        try:
            buy_fee_rate = _finite_number(EXCHANGE_FEES[actual_buy_exchange][market_type], "buy_fee_rate")
        except KeyError as exc:
            raise ValueError(
                f"No configured {market_type} fee for buy exchange: {actual_buy_exchange}"
            ) from exc

    if custom_sell_fee is not None:
        sell_fee_rate = _finite_number(custom_sell_fee, "custom_sell_fee")
    else:
        try:
            sell_fee_rate = _finite_number(EXCHANGE_FEES[actual_sell_exchange][market_type], "sell_fee_rate")
        except KeyError as exc:
            raise ValueError(
                f"No configured {market_type} fee for sell exchange: {actual_sell_exchange}"
            ) from exc

    if not 0 <= buy_fee_rate <= 1 or not 0 <= sell_fee_rate <= 1:
        raise ValueError("Exchange fee rates must be between 0 and 1 (fraction, not percent)")

    gross_buy_cost = actual_buy_price * actual_volume
    gross_sell_revenue = actual_sell_price * actual_volume
    gross_profit_usd = gross_sell_revenue - gross_buy_cost
    gross_profit_pct = (gross_profit_usd / gross_buy_cost) * 100.0

    buy_fee_usd = gross_buy_cost * buy_fee_rate
    sell_fee_usd = gross_sell_revenue * sell_fee_rate
    total_fees_usd = buy_fee_usd + sell_fee_usd
    fees_pct = (total_fees_usd / gross_buy_cost) * 100.0

    # Percentages are expressed in percentage points: 0.05 means 0.05%.
    slippage_rate = slippage_pct / 100.0
    slippage_usd = gross_buy_cost * slippage_rate

    net_profit_usd = gross_profit_usd - total_fees_usd - slippage_usd - other_costs
    # Use one denominator (buy-side capital) so net USD and net % cannot drift
    # because the sell fee is calculated on sale proceeds rather than buy cost.
    net_profit_pct = (net_profit_usd / gross_buy_cost) * 100.0

    return {
        "gross_profit_usd": round(gross_profit_usd, 8),
        "gross_profit_pct": round(gross_profit_pct, 8),
        "buy_fee": buy_fee_rate,
        "sell_fee": sell_fee_rate,
        "buy_fee_usd": round(buy_fee_usd, 8),
        "sell_fee_usd": round(sell_fee_usd, 8),
        "total_fees_usd": round(total_fees_usd, 8),
        "fees_pct": round(fees_pct, 8),
        "slippage_usd": round(slippage_usd, 8),
        "slippage_pct": round(slippage_pct, 8),
        "other_costs_usd": round(other_costs, 8),
        "net_profit_usd": round(net_profit_usd, 8),
        "net_profit_pct": round(net_profit_pct, 8),
    }
