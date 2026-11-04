from dataclasses import dataclass
from decimal import Decimal
from typing import Optional


@dataclass(frozen=True)
class TopOfBook:
    symbol: str
    bid_price: Decimal
    bid_qty: Decimal
    ask_price: Decimal
    ask_qty: Decimal
    received_at: float
    update_id: Optional[int] = None
    source: str = "binance_ws"

    def __post_init__(self):
        if self.bid_price <= 0 or self.ask_price <= 0:
            raise ValueError("book prices must be positive")
        if self.bid_qty < 0 or self.ask_qty < 0:
            raise ValueError("book quantities cannot be negative")
        if self.bid_price > self.ask_price:
            raise ValueError("crossed order book")


@dataclass(frozen=True)
class DexPoolSnapshot:
    chain_id: int
    pair_address: str
    token0: str
    token1: str
    reserve0: Decimal
    reserve1: Decimal
    decimals0: int
    decimals1: int
    fee_bps: int
    block_timestamp: int
    received_at: float
    source: str = "pancakeswap_v2_rpc"

    def __post_init__(self):
        if self.reserve0 <= 0 or self.reserve1 <= 0:
            raise ValueError("pool reserves must be positive")
        if not 0 <= self.fee_bps < 10_000:
            raise ValueError("invalid pool fee")
        if not 0 <= self.decimals0 <= 36 or not 0 <= self.decimals1 <= 36:
            raise ValueError("invalid token decimals")

    def quote_exact_in(self, token_in: str, amount_in: Decimal) -> Decimal:
        """Return a constant-product V2 quote, including the configured pool fee."""
        if amount_in <= 0:
            raise ValueError("amount_in must be positive")
        token_in = token_in.lower()
        if token_in == self.token0.lower():
            reserve_in, reserve_out = self.reserve0, self.reserve1
        elif token_in == self.token1.lower():
            reserve_in, reserve_out = self.reserve1, self.reserve0
        else:
            raise ValueError("token_in is not part of this pool")
        amount_after_fee = amount_in * Decimal(10_000 - self.fee_bps) / Decimal(10_000)
        return (amount_after_fee * reserve_out) / (reserve_in + amount_after_fee)

    def mid_price_token1_per_token0(self) -> Decimal:
        return self.reserve1 / self.reserve0
