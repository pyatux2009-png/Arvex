# ArbX — Crypto Arbitrage Bot

ArbX is a Python/FastAPI + React dashboard for monitoring cross-exchange spot arbitrage. Keep it in PAPER mode while validating market data, costs and execution behavior.

## Supported Python version

The backend targets **CPython 3.14 (64-bit)**. Use Python 3.14 for the virtual environment and every backend command; do not mix packages installed by another Python version.

## Included

- Binance Spot and Bybit Spot public order-book WebSocket streams.
- Depth-aware VWAP calculations and net profitability estimates.
- Configurable fees, slippage and position limits.
- Continuous scanner with visible per-symbol market-data diagnostics.
- SQLite history for scan snapshots, positive opportunities, engine events and capital settings.
- Historical analytics endpoints and dashboard metrics.
- First-run account setup, password hashing (PBKDF2-HMAC-SHA256), expiring server-side sessions and HttpOnly session cookies.
- PAPER execution by default; live trading remains opt-in.

## Windows quick start

From the repository root, use PowerShell:

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

Open the Vite URL printed in the terminal (usually `http://localhost:5173`). On first visit, create a local username and a strong password of at least 12 characters. The first account setup is available only while no user exists in the database.

## Configuration

Important local defaults in `.env.example`:

- `TRADING_MODE=PAPER`
- `AUTO_EXECUTE=false`
- `DATABASE_URL=sqlite+aiosqlite:///./crypto_arb.db`
- `COOKIE_SECURE=false` for local HTTP development. Set it to `true` behind HTTPS in deployment.
- `SYMBOLS=BTCUSDT,ETHUSDT,SOLUSDT`

Do not commit API keys or a populated `.env`. Do not expose the development server to the public internet; the local dashboard is not a hardened public deployment.

## API

Public:
- `GET /api/health`
- `GET /api/auth/status`
- `POST /api/auth/setup` (first user only)
- `POST /api/auth/login`
- `POST /api/auth/logout`

Authenticated:
- `GET /api/status`
- `GET /api/opportunities/live`
- `GET /api/analytics/summary?hours=24`
- `GET /api/analytics/history?limit=100`
- `POST /api/engine/start`
- `POST /api/engine/stop`
- `POST /api/settings/capital`

## Verification

```powershell
.\.venv\Scripts\python.exe -m compileall -q app tests
.\.venv\Scripts\python.exe -m pytest -q
cd frontend
npm.cmd run build
```

History is diagnostic/analytical data, not a record of realized profit. A displayed opportunity is an estimate and does not guarantee both legs can fill at those prices.
