from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Query
from app.models.schemas import HealthCheckResponse
from app.config import settings
from app.runtime import get_runtime

router = APIRouter()


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
async def start_engine():
    rt = get_runtime()
    await rt.start()
    return {'status': 'started', 'engine': rt.engine.status()}


@router.post('/api/engine/stop')
async def stop_engine():
    rt = get_runtime()
    await rt.stop()
    return {'status': 'stopped', 'engine': rt.engine.status()}


@router.get('/api/opportunities')
async def opportunities(symbol: str = Query(default=None), capital_usd: float = Query(default=None, gt=0)):
    rt = get_runtime()
    symbol = (symbol or settings.symbols[0]).upper()
    capital = capital_usd or settings.max_trade_size_usd
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
    return {'opportunities': rt.engine.last_opportunities, 'updated_at': rt.engine.last_scan_at}


@router.post('/api/trade')
async def execute_trade(opportunity: dict):
    rt = get_runtime()
    result = await rt.executor.execute_arbitrage(opportunity)
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
async def set_capital(payload: dict):
    rt = get_runtime()
    try:
        capital = float(payload.get('capital_usd'))
    except (TypeError, ValueError):
        raise HTTPException(400, 'capital_usd must be a number')
    if capital <= 0:
        raise HTTPException(400, 'capital_usd must be greater than 0')
    if capital > settings.max_trade_size_usd:
        raise HTTPException(400, f'capital_usd exceeds safety limit of ${settings.max_trade_size_usd:.2f}')
    rt.engine.capital_usd = capital
    return {'capital_usd': capital, 'max_trade_size_usd': settings.max_trade_size_usd}
