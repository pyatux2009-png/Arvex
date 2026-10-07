# Crypto Arbitrage Bot — backend

This repository is the backend foundation for a spot inter-exchange arbitrage bot.

## Current layer

- Binance Spot REST market data and authenticated order endpoints.
- Bybit V5 Spot REST market data and authenticated order endpoints.
- Binance and Bybit public WebSocket order-book streams.
- Bybit snapshot/delta order-book merge.
- Depth-aware VWAP and concrete trade-size profitability.
- Configurable exchange fees, slippage and other costs.
- Safety Engine with size, loss, profit, liquidity and stale-book limits.
- Continuous `TradingEngine` scanner/executor loop.
- Optional automatic execution controlled by `AUTO_EXECUTE`.
- Strict order-state handling: unknown execution is never treated as filled.
- Client-order-id idempotency and status re-check after uncertain requests.
- Partial-fill recovery path.
- PAPER balances and IOC-style depth simulation.
- FastAPI endpoints for health, status, engine control, live opportunities and manual trade execution.

## Important architecture note

True cross-exchange spot arbitrage normally requires **pre-funded inventory on both exchanges**: quote currency on the buy exchange and the base asset on the sell exchange. The executor therefore performs a balance preflight before trading.

Transfers are not used as the critical path of an arbitrage trade because blockchain/exchange transfer latency can destroy the price edge.

## Modes

- `SCAN`: inspect opportunities without execution.
- `PAPER`: real public market data can be used by the runtime, while orders are simulated locally.
- `LIVE`: requires exchange credentials and `AUTO_EXECUTE=true`; it is intentionally opt-in.

For safety, keep `AUTO_EXECUTE=false` until PAPER results are understood.

## Run

```bash
python -m venv .venv
.venv\\Scripts\\activate
pip install -r requirements.txt
copy .env.example .env
python -m app.main
```

API:

```bash
uvicorn app.api.app:app --reload
```

Endpoints:

- `GET /api/health`
- `GET /api/status`
- `GET /api/opportunities?symbol=BTCUSDT&capital_usd=50`
- `GET /api/opportunities/live`
- `POST /api/engine/start`
- `POST /api/engine/stop`
- `POST /api/trade`

## Verification

```bash
python -m compileall -q app tests
pytest -q
```

Do not put API secrets into source code or commit `.env`.
