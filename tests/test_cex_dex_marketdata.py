from decimal import Decimal
import pytest

from app.cex_dex.binance_stream import BinanceBookTickerStream
from app.cex_dex.models import DexPoolSnapshot
from app.cex_dex.pancakeswap_v2 import (
    BSC_CHAIN_ID,
    DEFAULT_FACTORY,
    DEFAULT_USDT,
    DEFAULT_WBNB,
    PancakeSwapV2Client,
    _address_word,
    _decode_address,
    _decode_uint,
)
from app.cex_dex.service import CexDexMarketDataService


def word(value: int) -> str:
    return format(value, "064x")


def address_word(address: str) -> str:
    return address.lower().removeprefix("0x").rjust(64, "0")


def test_binance_bookticker_parser_uses_decimal_and_local_receive_time():
    book = BinanceBookTickerStream.parse_message(
        {"s": "BNBUSDT", "b": "600.10", "B": "2.5", "a": "600.20", "A": "1.2", "u": 42},
        received_at=123.0,
    )
    assert book.symbol == "BNBUSDT"
    assert book.bid_price == Decimal("600.10")
    assert book.ask_price == Decimal("600.20")
    assert book.bid_qty == Decimal("2.5")
    assert book.update_id == 42
    assert book.received_at == 123.0


def test_binance_bookticker_rejects_crossed_market():
    with pytest.raises(ValueError, match="crossed"):
        BinanceBookTickerStream.parse_message(
            {"s": "BNBUSDT", "b": "601", "B": "1", "a": "600", "A": "1"}
        )


def test_binance_bookticker_rejects_missing_fields():
    with pytest.raises(ValueError, match="invalid Binance"):
        BinanceBookTickerStream.parse_message({"s": "BNBUSDT"})


def test_abi_helpers_validate_and_decode_values():
    assert _address_word(DEFAULT_WBNB).endswith(DEFAULT_WBNB[2:].lower())
    assert _decode_uint("0x" + word(56)) == 56
    assert _decode_address("0x" + address_word(DEFAULT_USDT)) == DEFAULT_USDT.lower()
    with pytest.raises(ValueError, match="invalid EVM address"):
        _address_word("not-an-address")


def test_v2_pool_quote_applies_fee_and_price_impact():
    pool = DexPoolSnapshot(
        chain_id=BSC_CHAIN_ID,
        pair_address="0x" + "1" * 40,
        token0=DEFAULT_WBNB,
        token1=DEFAULT_USDT,
        reserve0=Decimal("10"),
        reserve1=Decimal("3000"),
        decimals0=18,
        decimals1=18,
        fee_bps=25,
        block_timestamp=1,
        received_at=100.0,
    )
    output = pool.quote_exact_in(DEFAULT_WBNB, Decimal("1"))
    assert Decimal("272") < output < Decimal("273")
    assert output < Decimal("300")  # constant-product price impact plus pool fee
    assert pool.mid_price_token1_per_token0() == Decimal("300")


def test_v2_pool_quote_rejects_unknown_token_and_nonpositive_input():
    pool = DexPoolSnapshot(56, "0x" + "1" * 40, DEFAULT_WBNB, DEFAULT_USDT,
                           Decimal("10"), Decimal("3000"), 18, 18, 25, 1, 1.0)
    with pytest.raises(ValueError, match="not part"):
        pool.quote_exact_in("0x" + "2" * 40, Decimal("1"))
    with pytest.raises(ValueError, match="positive"):
        pool.quote_exact_in(DEFAULT_WBNB, Decimal("0"))


@pytest.mark.asyncio
async def test_pancakeswap_client_initializes_pair_read_only():
    client = PancakeSwapV2Client("https://rpc.example")
    calls = []

    async def fake_rpc(method, params):
        calls.append((method, params))
        return "0x38"

    async def fake_eth_call(address, data):
        if address == DEFAULT_FACTORY:
            assert data.startswith("e6a43905")
            return "0x" + address_word("0x" + "a" * 40)
        if data == "0x0dfe1681":
            return "0x" + address_word(DEFAULT_WBNB)
        if data == "0xd21220a7":
            return "0x" + address_word(DEFAULT_USDT)
        if address.lower() == DEFAULT_WBNB.lower():
            return "0x" + word(18)
        if address.lower() == DEFAULT_USDT.lower():
            return "0x" + word(18)
        raise AssertionError("unexpected eth_call")

    client._rpc = fake_rpc
    client._eth_call = fake_eth_call
    pair = await client.initialize()
    assert pair == "0x" + "a" * 40
    assert client.chain_id == 56
    assert client.decimals0 == 18 and client.decimals1 == 18
    assert calls == [("eth_chainId", [])]
    await client.close()


@pytest.mark.asyncio
async def test_pancakeswap_client_rejects_wrong_chain():
    client = PancakeSwapV2Client("https://rpc.example")

    async def fake_rpc(method, params):
        return "0x1"

    client._rpc = fake_rpc
    with pytest.raises(RuntimeError, match="wrong chain"):
        await client.initialize()
    await client.close()


@pytest.mark.asyncio
async def test_pancakeswap_snapshot_decodes_reserves():
    client = PancakeSwapV2Client("https://rpc.example")
    client.chain_id = 56
    client.pair_address = "0x" + "a" * 40
    client.token0 = DEFAULT_WBNB
    client.token1 = DEFAULT_USDT
    client.decimals0 = 18
    client.decimals1 = 18

    async def fake_eth_call(address, data):
        assert data == "0902f1ac"
        return "0x" + word(10 * 10**18) + word(3000 * 10**18) + word(123456)

    client._eth_call = fake_eth_call
    snapshot = await client.get_pool_snapshot()
    assert snapshot.reserve0 == Decimal("10")
    assert snapshot.reserve1 == Decimal("3000")
    assert snapshot.block_timestamp == 123456
    await client.close()


def test_market_data_status_is_explicitly_paper_and_wallet_disconnected():
    service = CexDexMarketDataService("https://rpc.example")
    status = service.status(now=100.0)
    assert status["mode"] == "PAPER"
    assert status["wallet_connected"] is False
    assert status["orders_enabled"] is False
    assert status["transactions_enabled"] is False


def test_dex_pool_price_is_normalized_to_usdt_per_bnb_for_both_token_orders():
    from app.cex_dex.service import CexDexMarketDataService

    bnb_first = DexPoolSnapshot(56, "0x" + "1" * 40, DEFAULT_WBNB, DEFAULT_USDT,
                                Decimal("10"), Decimal("3000"), 18, 18, 25, 1, 1.0)
    usdt_first = DexPoolSnapshot(56, "0x" + "1" * 40, DEFAULT_USDT, DEFAULT_WBNB,
                                 Decimal("3000"), Decimal("10"), 18, 18, 25, 1, 1.0)
    assert CexDexMarketDataService._pool_price_usdt_per_bnb(bnb_first) == "300"
    assert CexDexMarketDataService._pool_price_usdt_per_bnb(usdt_first) == "300"
