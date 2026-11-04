# ArbX — Crypto Arbitrage Bot

ArbX is a Python/FastAPI + React dashboard for monitoring crypto arbitrage. Keep all strategies in PAPER mode while validating market data, costs and execution behavior.

## Supported Python version
The backend targets **CPython 3.14 (64-bit)**. Use Python 3.14 for the virtual environment and every backend command.

## Included
- Binance Spot and Bybit Spot public order-book WebSocket streams for the original cross-exchange strategy.
- Depth-aware VWAP calculations and net profitability estimates.
- Configurable fees, slippage and position limits.
- Continuous scanner with market-data diagnostics.
- SQLite history and analytics.
- Authenticated local dashboard.
- PAPER execution by default; live trading remains opt-in in the original engine.

## CEX-DEX PAPER research profile (new)
The branch `feat/cex-dex-paper-marketdata` adds a separate, read-only CEX-DEX market-data foundation:
- Binance Spot public `BNBUSDT@bookTicker` WebSocket.
- PancakeSwap V2 BNB Chain pair discovery through the factory contract.
- Read-only BNB Chain JSON-RPC calls for pair tokens, decimals and reserves.
- Constant-product exact-input quote math with a configurable pool fee (default 25 bps).
- Data freshness/status reporting, including a normalized DEX BNB/USDT pool mid-price.
- Append-only JSONL market-data capture for the 30-day PAPER observation window.
- No Trust Wallet connection, private keys, token approvals, signed transactions, exchange orders or withdrawals.

The first CEX-DEX phase uses PancakeSwap V2 deliberately. V3 concentrated-liquidity quoting will be a separate implementation after the V2 feed and tests are validated.

### Run the CEX-DEX market-data monitor
Set the following in `.env` (or keep the defaults in `.env.example`):
```env
CEX_DEX_MODE=PAPER
CEX_DEX_SYMBOL=BNBUSDT
CEX_DEX_VIRTUAL_DEPOSIT_USDT=100
CEX_DEX_TEST_DAYS=30
CEX_DEX_BSC_RPC_URL=https://bsc-dataseed.binance.org
CEX_DEX_PANCAKE_V2_FEE_BPS=25
CEX_DEX_MARKETDATA_POLL_SECONDS=2
CEX_DEX_STALE_AFTER_SECONDS=5
```

Install dependencies and run:
```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe run_cex_dex_marketdata.py
```

The runner prints Binance top-of-book and PancakeSwap pool-reserve freshness and appends timestamped samples to `data/cex_dex_marketdata.jsonl` (configurable with `CEX_DEX_LOG_PATH`). It is a data monitor only, not a trading executor. Stop it with Ctrl+C.

## Windows quick start (existing dashboard)
```powershell
py -3.14 --version
py -3.14 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip setuptools wheel
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
if (!(Test-Path .env)) { Copy-Item .env.example .env }
.\.venv\Scripts\python.exe run_backend.py
```

In a second PowerShell window:
```powershell
cd frontend
npm.cmd install
npm.cmd run dev
```

Open the Vite URL printed in the terminal (usually `http://localhost:5173`). On first visit, create a local username and a strong password of at least 12 characters.

## Configuration and safety
- Do not commit API keys or a populated `.env`.
- Public market-data endpoints do not require Binance API credentials.
- Never enter a Trust Wallet seed phrase into ArbX.
- The CEX-DEX research runner is hard-guarded to PAPER mode and has no order-submission or transaction-signing code.
- Do not expose the development server to the public internet.

## Verification
```powershell
.\.venv\Scripts\python.exe -m compileall -q app tests
.\.venv\Scripts\python.exe -m pytest -q
cd frontend
npm.cmd run build
```

A displayed opportunity is an estimate and does not guarantee both legs can fill at those prices.
