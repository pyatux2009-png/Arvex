import hashlib
import hmac
import json
import os
import secrets
import time
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy import func, select
from app.models.schemas import HealthCheckResponse
from app.config import settings
from app.runtime import get_runtime
from app.database.database import AsyncSessionLocal
from app.database.models import AuthSession, EngineEvent, OpportunityHistory, ScanSnapshot, User
from app.database.service import save_setting

router = APIRouter()
SESSION_COOKIE = "arbx_session"
SESSION_TTL_SECONDS = 12 * 60 * 60
PBKDF2_ITERATIONS = 310_000


def _password_hash(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return "pbkdf2_sha256$" + str(PBKDF2_ITERATIONS) + "$" + salt.hex() + "$" + digest.hex()


def _verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, iterations, salt_hex, digest_hex = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), int(iterations))
        return hmac.compare_digest(actual.hex(), digest_hex)
    except (ValueError, TypeError):
        return False


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        SESSION_COOKIE, token, max_age=SESSION_TTL_SECONDS, httponly=True,
        secure=os.getenv("COOKIE_SECURE", "false").strip().lower() in {"1", "true", "yes", "on"},
        samesite="lax", path="/",
    )


async def require_user(request: Request) -> int:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise HTTPException(status_code=401, detail="Authentication required")
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(AuthSession).where(
            AuthSession.token_hash == _token_hash(token), AuthSession.expires_at > time.time()
        ))
        session = result.scalar_one_or_none()
        if session is None:
            raise HTTPException(status_code=401, detail="Session expired; sign in again")
        return session.user_id


async def _create_session(response: Response, user: User) -> None:
    token = secrets.token_urlsafe(32)
    now = time.time()
    async with AsyncSessionLocal() as db:
        db.add(AuthSession(user_id=user.id, token_hash=_token_hash(token), created_at=now, expires_at=now + SESSION_TTL_SECONDS))
        await db.commit()
    _set_session_cookie(response, token)


@router.get("/api/auth/status")
async def auth_status(request: Request):
    async with AsyncSessionLocal() as db:
        user_count = int(await db.scalar(select(func.count(User.id))) or 0)
        token = request.cookies.get(SESSION_COOKIE)
        if token:
            result = await db.execute(select(AuthSession, User).join(User, User.id == AuthSession.user_id).where(
                AuthSession.token_hash == _token_hash(token), AuthSession.expires_at > time.time()
            ))
            pair = result.first()
            if pair:
                return {"authenticated": True, "username": pair[1].username, "setup_required": False}
        return {"authenticated": False, "setup_required": user_count == 0}


@router.post("/api/auth/setup")
async def auth_setup(payload: dict, response: Response):
    username = str(payload.get("username", "")).strip()
    password = str(payload.get("password", ""))
    if len(username) < 3 or len(username) > 80:
        raise HTTPException(400, "Username must be 3–80 characters")
    if len(password) < 12:
        raise HTTPException(400, "Password must contain at least 12 characters")
    async with AsyncSessionLocal() as db:
        count = int(await db.scalar(select(func.count(User.id))) or 0)
        if count:
            raise HTTPException(409, "Initial setup is already complete; please sign in")
        user = User(username=username, password_hash=_password_hash(password), created_at=time.time())
        db.add(user)
        await db.commit()
        await db.refresh(user)
    await _create_session(response, user)
    return {"authenticated": True, "username": username}


@router.post("/api/auth/login")
async def auth_login(payload: dict, response: Response):
    username = str(payload.get("username", "")).strip()
    password = str(payload.get("password", ""))
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User).where(User.username == username))
        user = result.scalar_one_or_none()
        if user is None or not _verify_password(password, user.password_hash):
            raise HTTPException(401, "Incorrect username or password")
    await _create_session(response, user)
    return {"authenticated": True, "username": user.username}


@router.post("/api/auth/logout")
async def auth_logout(request: Request, response: Response):
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(AuthSession).where(AuthSession.token_hash == _token_hash(token)))
            session = result.scalar_one_or_none()
            if session:
                await db.delete(session)
                await db.commit()
    response.delete_cookie(SESSION_COOKIE, path="/", httponly=True, samesite="lax")
    return {"authenticated": False}


@router.get("/api/health", response_model=HealthCheckResponse)
async def health_check():
    return HealthCheckResponse(status="healthy", mode=settings.trading_mode, timestamp=datetime.now(timezone.utc))


@router.get("/api/status")
async def get_status(user_id: int = Depends(require_user)):
    rt = get_runtime()
    return {
        "status": "running", "started": rt.started, "mode": settings.trading_mode,
        "live_trading": settings.live_trading, "auto_execute": rt.engine.auto_execute,
        "symbols": list(settings.symbols), "max_trade_size_usd": settings.max_trade_size_usd,
        "engine": rt.engine.status(),
    }


@router.post("/api/engine/start")
async def start_engine(user_id: int = Depends(require_user)):
    rt = get_runtime()
    await rt.start()
    return {"status": "started", "engine": rt.engine.status()}


@router.post("/api/engine/stop")
async def stop_engine(user_id: int = Depends(require_user)):
    rt = get_runtime()
    await rt.stop()
    return {"status": "stopped", "engine": rt.engine.status()}


@router.get("/api/opportunities")
async def opportunities(symbol: str = Query(default=None), capital_usd: float = Query(default=None, gt=0), user_id: int = Depends(require_user)):
    rt = get_runtime()
    symbol = (symbol or settings.symbols[0]).upper()
    capital = capital_usd or rt.engine.capital_usd
    if symbol not in settings.symbols:
        raise HTTPException(400, f"Symbol {symbol} is not enabled")
    return {"symbol": symbol, "capital_usd": capital, "opportunities": await rt.scanner.scan_opportunities(symbol, capital)}


@router.get("/api/opportunities/live")
async def live_opportunities(user_id: int = Depends(require_user)):
    rt = get_runtime()
    return {"opportunities": rt.engine.last_opportunities, "updated_at": rt.engine.last_scan_at,
            "diagnostics": rt.scanner.diagnostics_by_symbol}


@router.post("/api/trade")
async def execute_trade(opportunity: dict, user_id: int = Depends(require_user)):
    rt = get_runtime()
    return await rt.executor.execute_arbitrage(opportunity)


@router.get("/api/settings")
async def get_settings(user_id: int = Depends(require_user)):
    rt = get_runtime()
    return {"capital_usd": rt.engine.capital_usd, "max_trade_size_usd": settings.max_trade_size_usd,
            "mode": settings.trading_mode, "auto_execute": rt.engine.auto_execute, "symbols": list(settings.symbols)}


@router.post("/api/settings/capital")
async def set_capital(payload: dict, user_id: int = Depends(require_user)):
    rt = get_runtime()
    try:
        capital = float(payload.get("capital_usd"))
    except (TypeError, ValueError):
        raise HTTPException(400, "capital_usd must be a number")
    if capital <= 0:
        raise HTTPException(400, "capital_usd must be greater than 0")
    if capital > settings.max_trade_size_usd:
        raise HTTPException(400, f"capital_usd exceeds safety limit of ${settings.max_trade_size_usd:.2f}")
    rt.engine.capital_usd = capital
    await save_setting("capital_usd", capital)
    return {"capital_usd": capital, "max_trade_size_usd": settings.max_trade_size_usd}


@router.get("/api/analytics/summary")
async def analytics_summary(hours: int = Query(default=24, ge=1, le=720), user_id: int = Depends(require_user)):
    since = time.time() - hours * 3600
    async with AsyncSessionLocal() as db:
        scans = int(await db.scalar(select(func.count(ScanSnapshot.id)).where(ScanSnapshot.created_at >= since)) or 0)
        unique_symbols = int(await db.scalar(select(func.count(func.distinct(ScanSnapshot.symbol))).where(ScanSnapshot.created_at >= since)) or 0)
        opportunity_rows = int(await db.scalar(select(func.count(OpportunityHistory.id)).where(OpportunityHistory.created_at >= since)) or 0)
        best_net = await db.scalar(select(func.max(OpportunityHistory.net_profit_pct)).where(OpportunityHistory.created_at >= since))
        best_gross = await db.scalar(select(func.max(ScanSnapshot.max_gross_profit_pct)).where(ScanSnapshot.created_at >= since))
        scan_result = await db.execute(select(ScanSnapshot).where(ScanSnapshot.created_at >= since).order_by(ScanSnapshot.created_at.desc()).limit(100))
        scan_rows = scan_result.scalars().all()
        event_result = await db.execute(select(EngineEvent).where(EngineEvent.created_at >= since).order_by(EngineEvent.created_at.desc()).limit(20))
        events = event_result.scalars().all()
    latest_by_symbol = {}
    for row in scan_rows:
        if row.symbol not in latest_by_symbol:
            latest_by_symbol[row.symbol] = {
                "symbol": row.symbol, "books_available": row.books_available,
                "evaluated_routes": row.evaluated_routes, "positive_opportunities": row.positive_opportunities,
                "errors": row.errors, "max_gross_profit_pct": row.max_gross_profit_pct,
                "max_net_profit_pct": row.max_net_profit_pct, "created_at": row.created_at,
                "diagnostics": json.loads(row.diagnostics_json or "{}"),
            }
    return {
        "hours": hours, "scan_snapshots": scans, "symbols_seen": unique_symbols,
        "opportunity_history_rows": opportunity_rows, "best_net_profit_pct": float(best_net or 0),
        "best_gross_profit_pct": float(best_gross or 0), "latest_by_symbol": list(latest_by_symbol.values()),
        "recent_events": [{"created_at": e.created_at, "level": e.level, "event": e.event, "message": e.message} for e in events],
    }


@router.get("/api/analytics/history")
async def analytics_history(limit: int = Query(default=100, ge=1, le=1000), user_id: int = Depends(require_user)):
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(OpportunityHistory).order_by(OpportunityHistory.created_at.desc()).limit(limit))
        rows = result.scalars().all()
    return {"items": [{
        "created_at": row.created_at, "symbol": row.symbol, "buy_exchange": row.buy_exchange,
        "sell_exchange": row.sell_exchange, "buy_price": row.buy_price, "sell_price": row.sell_price,
        "position_size": row.position_size, "gross_profit_pct": row.gross_profit_pct,
        "net_profit_pct": row.net_profit_pct, "net_profit_usd": row.net_profit_usd,
    } for row in rows]}
