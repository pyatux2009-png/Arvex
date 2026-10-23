import hmac
import os
import math
from datetime import datetime, timezone

from fastapi import APIRouter, Header, HTTPException, Query
from app.models.schemas import HealthCheckResponse
from app.config import settings
from app.runtime import get_runtime

router = APIRouter()


def _require_live_api_token(x_api_token: str | None) -> None:
    """Protect mutating API routes whenever the backend is configured for LIVE."""
    if not settings.live_trading:
        return
    configured_token = os.getenv('LIVE_API_TOKEN', '').strip()
    if not configured_token:
        raise HTTPException(503, 'LIVE trading is disabled until LIVE_API_TOKEN is configured.')
    if not x_api_token or not hmac.compare_digest(x_api_token, configured_token):
        raise HTTPException(401, 'Valid X-API-Token header required for LIVE trading.')


@router.get('/api/health', response_model=HealthCheckResponse)
async def health_check():
    return HealthCheckResponse(status='healthy', mode=settings.trading_mode, timestamp=datetime.now(timezone.utc))


@router.get('/api/status')
async def get_status():
    rt = get_runtime()
    return {
        'status': 'running',
        'started': rt.started,
        'mode': settings.trading_mode,
        'live_trading': settings.live_trading,
        'auto_execute': rt.engine.auto_execute,
        'symbols': list(settings.symbols),
        'max_trade_size_usd': settings.max_trade_size_usd,
        'engine': rt.engine.status(),
    }


@router.post('/api/engine/start')
async def start_engine(x_api_token: str | None = Header(default=None)):
    _require_live_api_token(x_api_token)
    rt = get_runtime()
    await rt.start()
    return {'status': 'started', 'engine': rt.engine.status()}


@router.post('/api/engine/stop')
async def stop_engine(x_api_token: str | None = Header(default=None)):
    _require_live_api_token(x_api_token)
    rt = get_runtime()
    await rt.stop()
    return {'status': 'stopped', 'engine': rt.engine.status()}


@router.get('/api/opportunities')
async def opportunities(symbol: str = Query(default=None), capital_usd: float = Query(default=None, gt=0)):
    rt = get_runtime()
    symbol = (symbol or settings.symbols[0]).upper()
    capital = capital_usd or settings.max_trade_size_usd
    if not math.isfinite(capital) or capital > settings.max_trade_size_usd:
        raise HTTPException(400, f'capital_usd must not exceed safety limit of ${settings.max_trade_size_usd:.2f}')
    if symbol not in settings.symbols:
        raise HTTPException(400, f'Symbol {symbol} is not enabled')
    return {
        'symbol': symbol,
        'capital_usd': capital,
        'opportunities': await rt.scanner.scan_opportunities(symbol, capital),
    }


@router.get('/api/opportunities/live')
async def live_opportunities():
    rt = get_runtime()
    return {'opportunities': rt.engine.last_opportunities, 'updated_at': rt.engine.last_scan_at, 'diagnostics': rt.scanner.diagnostics_by_symbol}


@router.post('/api/trade')
async def execute_trade(opportunity: dict, x_api_token: str | None = Header(default=None)):
    rt = get_runtime()

    _require_live_api_token(x_api_token)

    symbol = str(opportunity.get('symbol', '')).upper()
    buy_exchange = str(opportunity.get('buy_exchange', '')).lower()
    sell_exchange = str(opportunity.get('sell_exchange', '')).lower()
    if symbol not in settings.symbols:
        raise HTTPException(400, f'Symbol {symbol or "(missing)"} is not enabled')
    if buy_exchange == sell_exchange or buy_exchange not in rt.trade_exchanges or sell_exchange not in rt.trade_exchanges:
        raise HTTPException(400, 'Trade must use two distinct execution-enabled exchanges (Binance/Bybit).')

    # Do not trust client-supplied prices, quantity, profit, liquidity or risk.
    # Re-scan now and execute only a fresh server-generated candidate matching
    # the requested route. The requested size is clamped to the configured cap.
    try:
        requested_capital = float(opportunity.get('position_size', rt.engine.capital_usd))
    except (TypeError, ValueError):
        raise HTTPException(400, 'position_size must be numeric')
    if not math.isfinite(requested_capital) or requested_capital <= 0:
        raise HTTPException(400, 'position_size must be finite and greater than zero')
    capital = min(requested_capital, settings.max_trade_size_usd)
    fresh_candidates = await rt.scanner.scan_opportunities(symbol, capital)
    fresh = next((
        item for item in fresh_candidates
        if item.get('buy_exchange') == buy_exchange
        and item.get('sell_exchange') == sell_exchange
        and item.get('execution_supported') is True
    ), None)
    if fresh is None:
        raise HTTPException(409, 'The requested route is no longer a fresh, profitable, executable opportunity.')

    result = await rt.executor.execute_arbitrage(fresh)
    return result


@router.get('/api/settings')
async def get_settings():
    rt = get_runtime()
    return {
        'capital_usd': rt.engine.capital_usd,
        'max_trade_size_usd': settings.max_trade_size_usd,
        'mode': settings.trading_mode,
        'auto_execute': rt.engine.auto_execute,
        'symbols': list(settings.symbols),
    }


@router.post('/api/settings/capital')
async def set_capital(payload: dict, x_api_token: str | None = Header(default=None)):
    _require_live_api_token(x_api_token)
    rt = get_runtime()
    try:
        capital = float(payload.get('capital_usd'))
    except (TypeError, ValueError):
        raise HTTPException(400, 'capital_usd must be a number')
    if not math.isfinite(capital) or capital <= 0:
        raise HTTPException(400, 'capital_usd must be finite and greater than 0')
    if capital > settings.max_trade_size_usd:
        raise HTTPException(400, f'capital_usd exceeds safety limit of ${settings.max_trade_size_usd:.2f}')
    rt.engine.capital_usd = capital
    return {'capital_usd': capital, 'max_trade_size_usd': settings.max_trade_size_usd}
