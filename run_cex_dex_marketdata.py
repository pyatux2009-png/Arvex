import asyncio
import json
import logging
import os
import time
from pathlib import Path

from dotenv import load_dotenv

from app.cex_dex.service import CexDexMarketDataService\nfrom app.cex_dex.scanner import CexDexPaperScanner

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
    log_interval = float(os.getenv("CEX_DEX_LOG_INTERVAL_SECONDS", "5"))
    log_path = Path(os.getenv("CEX_DEX_LOG_PATH", "data/cex_dex_marketdata.jsonl"))
    log_path.parent.mkdir(parents=True, exist_ok=True)
    dex_fee_bps = int(os.getenv("CEX_DEX_PANCAKE_V2_FEE_BPS", "25"))\n    quote_sizes = [float(value.strip()) for value in os.getenv("CEX_DEX_QUOTE_SIZES_USDT", "10,25,50,100").split(",") if value.strip()]\n    if not quote_sizes or any(value <= 0 for value in quote_sizes):\n        raise ValueError("CEX_DEX_QUOTE_SIZES_USDT must contain positive values")\n    if max(quote_sizes) > float(os.getenv("CEX_DEX_VIRTUAL_DEPOSIT_USDT", "100")):\n        raise ValueError("quote size cannot exceed the configured virtual PAPER deposit")\n    scanner = CexDexPaperScanner(\n        cex_fee_bps=int(os.getenv("CEX_DEX_BINANCE_FEE_BPS", "10")),\n        gas_cost_usdt=__import__("decimal").Decimal(os.getenv("CEX_DEX_ESTIMATED_GAS_USDT", "0.05")),\n        stale_after_seconds=stale_seconds,\n    )

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
        with log_path.open("a", encoding="utf-8") as history:
            while True:
                now = time.time()\n                opportunities = []\n                if service.binance.latest is not None and service.dex_latest is not None:\n                    opportunities = scanner.scan(\n                        service.binance.latest, service.dex_latest, quote_sizes, now=now\n                    )\n                record = {"logged_at": now, **service.status(), "paper_opportunities": opportunities}
                line = json.dumps(record, ensure_ascii=False)
                logger.info("market_data=%s", line)
                history.write(line + "\n")
                history.flush()
                await asyncio.sleep(log_interval)
    finally:
        await service.stop()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
