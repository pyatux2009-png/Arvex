# Arvex — Spot Arbitrage Platform

Arvex is a spot inter-exchange arbitrage research and execution platform.

This repository is the backend foundation for a spot inter-exchange arbitrage bot.

The default scanner universe contains 24 USDT spot pairs: BTC, ETH, SOL, BNB, XRP, DOGE, ADA, LINK, AVAX, LTC, BCH, TRX, DOT, TON, XLM, UNI, ATOM, NEAR, ETC, SUI, FIL, AAVE, ARB and OP. These are a liquid large-cap starting set, not a guarantee of stable prices or profitable arbitrage. The `SYMBOLS` environment variable can override the list. Binance/Bybit are the only execution venues; OKX/Kraken are discovery-only.

## Current layer

- Binance Spot REST market data and authenticated order endpoints.
- Bybit V5 Spot REST market data and authenticated order endpoints.
- Binance, Bybit, OKX and Kraken public WebSocket order-book streams with REST fallback.
- Read-only OKX and Kraken Spot order-book discovery; these venues are not enabled for execution.
- Bybit snapshot/delta order-book merge.
- Depth-aware VWAP and concrete trade-size profitability.
- Per-symbol scanner diagnostics: book freshness, API errors, evaluated routes, gross-positive routes, cost-erased spreads and best gross candidate.
- Net ROI uses the same buy-capital denominator as net USD P&L.
- Configurable exchange fees, slippage and other costs.
- Safety Engine with size, loss, profit, liquidity and stale-book limits.
- Manual trade endpoint re-scans server-side and does not trust client-supplied PnL, prices, quantity, liquidity or risk fields.
- Binance/Bybit execution preflight checks cached market status, quantity step, minimum quantity/notional and price tick rules; metadata errors block execution.
- LIVE order submission fails closed unless `LIVE_API_TOKEN` is configured; manual LIVE requests must send it as `X-API-Token`. Engine start/stop and capital-setting mutations also require this token in LIVE mode.
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
- `LIVE`: requires exchange credentials and `AUTO_EXECUTE=true`; manual LIVE requests additionally require `LIVE_API_TOKEN` in the `X-API-Token` header. The executor also blocks LIVE submission when the token is absent. Keep LIVE disabled until the complete order-price/lot-size path has passed exchange-specific smoke tests.

For safety, keep `AUTO_EXECUTE=false` until PAPER results are understood. OKX/Kraken results are discovery-only; a displayed positive estimate is not an executable trade and can change before execution. Set exchange fee estimates to your actual account tier in `.env`.

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
- `GET /api/opportunities/live` (includes per-symbol `diagnostics`)
- `POST /api/engine/start`
- `POST /api/engine/stop`
- `POST /api/trade`

## Verification

```bash
python -m compileall -q app tests
pytest -q
```

Do not put API secrets into source code or commit `.env`. `LIVE_API_TOKEN` is a local secret and must never be committed.
