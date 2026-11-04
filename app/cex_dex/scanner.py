"""Read-only CEX/DEX quote scanner. Estimates both routes; never places orders."""
from dataclasses import asdict, dataclass
from decimal import Decimal
from typing import Iterable, Optional

from app.cex_dex.models import DexPoolSnapshot, TopOfBook
from app.cex_dex.pancakeswap_v2 import DEFAULT_USDT, DEFAULT_WBNB


@dataclass(frozen=True)
class ArbitrageQuote:
    mode: str
    symbol: str
    direction: str
    quote_size_usdt: str
    input_asset: str
    input_amount: str
    intermediate_bnb: str
    output_usdt: str
    cex_price: str
    dex_marginal_price: str
    cex_fee_usdt: str
    dex_fee_bps: int
    estimated_gas_usdt: str
    net_profit_usdt: str
    net_profit_pct: str
    executable_at_top_of_book: bool
    rejection_reason: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


class CexDexPaperScanner:
    """Quote two routes against current Binance top-of-book and Pancake V2 reserves."""

    def __init__(
        self,
        cex_fee_bps: int = 10,
        gas_cost_usdt: Decimal = Decimal("0.05"),
        stale_after_seconds: float = 5.0,
    ):
        if not 0 <= cex_fee_bps < 10_000:
            raise ValueError("invalid CEX fee")
        if gas_cost_usdt < 0 or stale_after_seconds <= 0:
            raise ValueError("gas cost must be nonnegative and stale threshold positive")
        self.cex_fee_bps = cex_fee_bps
        self.gas_cost_usdt = gas_cost_usdt
        self.stale_after_seconds = stale_after_seconds

    @staticmethod
    def _dex_mid_price(pool: DexPoolSnapshot) -> Decimal:
        if pool.token0.lower() == DEFAULT_WBNB.lower() and pool.token1.lower() == DEFAULT_USDT.lower():
            return pool.reserve1 / pool.reserve0
        if pool.token1.lower() == DEFAULT_WBNB.lower() and pool.token0.lower() == DEFAULT_USDT.lower():
            return pool.reserve0 / pool.reserve1
        raise ValueError("PancakeSwap pool is not the configured WBNB/USDT pair")

    @staticmethod
    def _validate_quote_sizes(sizes: Iterable[Decimal]) -> list[Decimal]:
        values = sorted(set(Decimal(str(value)) for value in sizes))
        if not values or any(value <= 0 for value in values):
            raise ValueError("quote sizes must contain positive USDT amounts")
        return values

    def scan(
        self,
        book: TopOfBook,
        pool: DexPoolSnapshot,
        quote_sizes_usdt: Iterable[Decimal],
        now: Optional[float] = None,
    ) -> list[dict]:
        import time
        now = time.time() if now is None else now
        if book.symbol != "BNBUSDT":
            raise ValueError("scanner currently supports BNBUSDT only")
        if now - book.received_at > self.stale_after_seconds or now - pool.received_at > self.stale_after_seconds:
            return []
        mid = self._dex_mid_price(pool)
        fee_factor = Decimal(10_000 - self.cex_fee_bps) / Decimal(10_000)
        results = []
        for budget in self._validate_quote_sizes(quote_sizes_usdt):
            # Route A: spend USDT on Binance ask, then sell received BNB into Pancake V2.
            bnb_bought = budget / (book.ask_price * (Decimal(1) + Decimal(self.cex_fee_bps) / Decimal(10_000)))
            cex_buy_fee = budget - bnb_bought * book.ask_price
            dex_sell_usdt = pool.quote_exact_in(DEFAULT_WBNB, bnb_bought)
            net_a = dex_sell_usdt - budget - self.gas_cost_usdt
            reason_a = None
            if bnb_bought > book.ask_qty:
                reason_a = "Binance ask top-level quantity is insufficient"
            results.append(ArbitrageQuote(
                mode="PAPER", symbol=book.symbol,
                direction="BUY_BINANCE_SELL_PANCAKESWAP",
                quote_size_usdt=str(budget), input_asset="USDT",
                input_amount=str(budget), intermediate_bnb=str(bnb_bought),
                output_usdt=str(dex_sell_usdt), cex_price=str(book.ask_price),
                dex_marginal_price=str(mid), cex_fee_usdt=str(cex_buy_fee),
                dex_fee_bps=pool.fee_bps, estimated_gas_usdt=str(self.gas_cost_usdt),
                net_profit_usdt=str(net_a), net_profit_pct=str(net_a / budget * 100),
                executable_at_top_of_book=reason_a is None, rejection_reason=reason_a,
            ).to_dict())

            # Route B: spend USDT on Pancake V2, then sell resulting BNB into Binance bid.
            bnb_bought_dex = pool.quote_exact_in(DEFAULT_USDT, budget)
            cex_gross = bnb_bought_dex * book.bid_price
            cex_sell_fee = cex_gross * (Decimal(1) - fee_factor)
            net_b = cex_sell_fee - budget - self.gas_cost_usdt
            reason_b = None
            if bnb_bought_dex > book.bid_qty:
                reason_b = "Binance bid top-level quantity is insufficient"
            results.append(ArbitrageQuote(
                mode="PAPER", symbol=book.symbol,
                direction="BUY_PANCAKESWAP_SELL_BINANCE",
                quote_size_usdt=str(budget), input_asset="USDT",
                input_amount=str(budget), intermediate_bnb=str(bnb_bought_dex),
                output_usdt=str(cex_sell_fee), cex_price=str(book.bid_price),
                dex_marginal_price=str(mid), cex_fee_usdt=str(cex_gross - cex_sell_fee),
                dex_fee_bps=pool.fee_bps, estimated_gas_usdt=str(self.gas_cost_usdt),
                net_profit_usdt=str(net_b), net_profit_pct=str(net_b / budget * 100),
                executable_at_top_of_book=reason_b is None, rejection_reason=reason_b,
            ).to_dict())
        return results
