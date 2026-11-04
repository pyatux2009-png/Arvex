import itertools
import time
from decimal import Decimal
from typing import Optional

import aiohttp

from app.cex_dex.models import DexPoolSnapshot

BSC_CHAIN_ID = 56
DEFAULT_FACTORY = "0xcA143Ce32Fe78f1f7019d7d551a6402fC5350c73"
DEFAULT_WBNB = "0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c"
DEFAULT_USDT = "0x55d398326f99059fF775485246999027B3197955"
SELECTOR_GET_PAIR = "e6a43905"
SELECTOR_TOKEN0 = "0dfe1681"
SELECTOR_TOKEN1 = "d21220a7"
SELECTOR_GET_RESERVES = "0902f1ac"
SELECTOR_DECIMALS = "313ce567"


def _address_word(address: str) -> str:
    value = address.lower().removeprefix("0x")
    if len(value) != 40 or any(c not in "0123456789abcdef" for c in value):
        raise ValueError("invalid EVM address")
    return value.rjust(64, "0")


def _decode_uint(hex_value: str) -> int:
    value = hex_value.removeprefix("0x")
    if len(value) < 64:
        raise ValueError("short ABI uint response")
    return int(value[-64:], 16)


def _decode_address(hex_value: str) -> str:
    value = hex_value.removeprefix("0x")
    if len(value) < 64:
        raise ValueError("short ABI address response")
    return "0x" + value[-40:]


class PancakeSwapV2Client:
    """Read-only BNB Chain PancakeSwap V2 pool reader; no wallet or signing code."""

    def __init__(
        self,
        rpc_url: str,
        token_a: str = DEFAULT_WBNB,
        token_b: str = DEFAULT_USDT,
        factory: str = DEFAULT_FACTORY,
        fee_bps: int = 25,
        session: Optional[aiohttp.ClientSession] = None,
    ):
        if not rpc_url.startswith(("https://", "http://")):
            raise ValueError("rpc_url must be HTTP(S)")
        if not 0 <= fee_bps < 10_000:
            raise ValueError("invalid fee_bps")
        _address_word(token_a)
        _address_word(token_b)
        _address_word(factory)
        self.rpc_url = rpc_url
        self.token_a = token_a
        self.token_b = token_b
        self.factory = factory
        self.fee_bps = fee_bps
        self.session = session
        self._owns_session = session is None
        self._ids = itertools.count(1)
        self.pair_address: Optional[str] = None
        self.token0: Optional[str] = None
        self.token1: Optional[str] = None
        self.decimals0: Optional[int] = None
        self.decimals1: Optional[int] = None
        self.chain_id: Optional[int] = None

    async def _ensure_session(self):
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10))
            self._owns_session = True

    async def _rpc(self, method: str, params: list):
        await self._ensure_session()
        payload = {"jsonrpc": "2.0", "id": next(self._ids), "method": method, "params": params}
        async with self.session.post(self.rpc_url, json=payload) as response:
            response.raise_for_status()
            body = await response.json()
        if body.get("error"):
            raise RuntimeError(f"BSC RPC error: {body['error']}")
        if "result" not in body:
            raise RuntimeError("malformed BSC RPC response")
        return body["result"]

    async def _eth_call(self, address: str, data: str) -> str:
        result = await self._rpc("eth_call", [{"to": address, "data": "0x" + data}, "latest"])
        if not isinstance(result, str) or not result.startswith("0x"):
            raise RuntimeError("malformed eth_call result")
        return result

    async def initialize(self):
        self.chain_id = int(await self._rpc("eth_chainId", []), 16)
        if self.chain_id != BSC_CHAIN_ID:
            raise RuntimeError(f"wrong chain: expected BNB Smart Chain {BSC_CHAIN_ID}, got {self.chain_id}")
        pair_result = await self._eth_call(self.factory, SELECTOR_GET_PAIR + _address_word(self.token_a) + _address_word(self.token_b))
        pair = _decode_address(pair_result)
        if int(pair[2:], 16) == 0:
            raise RuntimeError("PancakeSwap V2 pair not found for configured tokens")
        self.pair_address = pair
        self.token0 = _decode_address(await self._eth_call(pair, SELECTOR_TOKEN0))
        self.token1 = _decode_address(await self._eth_call(pair, SELECTOR_TOKEN1))
        self.decimals0 = _decode_uint(await self._eth_call(self.token0, SELECTOR_DECIMALS))
        self.decimals1 = _decode_uint(await self._eth_call(self.token1, SELECTOR_DECIMALS))
        if self.token_a.lower() not in {self.token0.lower(), self.token1.lower()} or self.token_b.lower() not in {self.token0.lower(), self.token1.lower()}:
            raise RuntimeError("factory returned a pair with unexpected tokens")
        return self.pair_address

    async def get_pool_snapshot(self) -> DexPoolSnapshot:
        if not self.pair_address:
            await self.initialize()
        raw = (await self._eth_call(self.pair_address, SELECTOR_GET_RESERVES)).removeprefix("0x")
        if len(raw) < 192:
            raise RuntimeError("malformed getReserves response")
        reserve0_raw = int(raw[0:64], 16)
        reserve1_raw = int(raw[64:128], 16)
        block_timestamp = int(raw[128:192], 16)
        reserve0 = Decimal(reserve0_raw) / (Decimal(10) ** self.decimals0)
        reserve1 = Decimal(reserve1_raw) / (Decimal(10) ** self.decimals1)
        return DexPoolSnapshot(
            chain_id=self.chain_id,
            pair_address=self.pair_address,
            token0=self.token0,
            token1=self.token1,
            reserve0=reserve0,
            reserve1=reserve1,
            decimals0=self.decimals0,
            decimals1=self.decimals1,
            fee_bps=self.fee_bps,
            block_timestamp=block_timestamp,
            received_at=time.time(),
        )

    async def close(self):
        if self._owns_session and self.session and not self.session.closed:
            await self.session.close()
            self.session = None
