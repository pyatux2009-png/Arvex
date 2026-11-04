import asyncio
import json
import logging
import os

from dotenv import load_dotenv

from app.cex_dex.service import CexDexMarketDataService

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("CEX-DEX-PAPER")


async def main():
    mode = os.getenv("CEX_DEX_MODE", "PAPER").upper()
    if mode != "PAPER":
        raise RuntimeError("CEX-DEX market-data runner is PAPER-only; live mode is not implemented")

    symbol = os.getenv("CEX_DEX_SYMBOL", "BNBUSDT").upper()
    rpc_url = os.getenv("CEX_DEX_BSC_RPC_URL", "https://bsc-dataseed.binance.org")
    poll_seconds = float(os.getenv("CEX_DEX_MARKETDATA_POLL_SECONDS", "2"))
    stale_seconds = float(os.getenv("CEX_DEX_STALE_AFTER_SECONDS", "5"))
    dex_fee_bps = int(os.getenv("CEX_DEX_PANCAKE_V2_FEE_BPS", "25"))

    service = CexDexMarketDataService(
        rpc_url=rpc_url,
        symbol=symbol,
        dex_poll_seconds=poll_seconds,
        stale_after_seconds=stale_seconds,
        dex_fee_bps=dex_fee_bps,
    )
    await service.start()
    logger.info("Started read-only CEX-DEX market data in PAPER mode for %s", symbol)
    try:
        while True:
            logger.info("market_data=%s", json.dumps(service.status(), ensure_ascii=False))
            await asyncio.sleep(5)
    finally:
        await service.stop()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
