import json
import time
from app.database.database import AsyncSessionLocal
from app.database.models import AppSetting, EngineEvent, OpportunityHistory, ScanSnapshot


async def save_setting(key: str, value: str) -> None:
    async with AsyncSessionLocal() as session:
        row = await session.get(AppSetting, key)
        if row is None:
            session.add(AppSetting(key=key, value=str(value)))
        else:
            row.value = str(value)
        await session.commit()


async def get_setting(key: str):
    async with AsyncSessionLocal() as session:
        row = await session.get(AppSetting, key)
        return row.value if row else None


async def record_engine_event(event: str, message: str = "", level: str = "INFO") -> None:
    async with AsyncSessionLocal() as session:
        session.add(EngineEvent(created_at=time.time(), event=event, message=message[:2000], level=level))
        await session.commit()


async def persist_scan_history(diagnostics_by_symbol: dict, opportunities: list, error_count: int) -> None:
    """Persist compact scan snapshots every few seconds, not every 250ms scan."""
    now = time.time()
    async with AsyncSessionLocal() as session:
        for symbol, diagnostic in diagnostics_by_symbol.items():
            session.add(ScanSnapshot(
                created_at=now, symbol=symbol,
                books_available=int(diagnostic.get("books_available", 0)),
                evaluated_routes=int(diagnostic.get("evaluated_routes", 0)),
                positive_opportunities=int(diagnostic.get("positive_opportunities", 0)),
                errors=int(error_count),
                max_gross_profit_pct=float(diagnostic.get("max_gross_profit_pct", 0.0)),
                max_net_profit_pct=float(diagnostic.get("max_net_profit_pct", 0.0)),
                diagnostics_json=json.dumps(diagnostic, separators=(",", ":")),
            ))
        for item in opportunities[:10]:
            session.add(OpportunityHistory(
                created_at=now, symbol=str(item.get("symbol", "")),
                buy_exchange=str(item.get("buy_exchange", "")), sell_exchange=str(item.get("sell_exchange", "")),
                buy_price=float(item.get("buy_price", 0.0)), sell_price=float(item.get("sell_price", 0.0)),
                position_size=float(item.get("position_size", 0.0)),
                gross_profit_pct=float(item.get("gross_profit_pct", 0.0)),
                net_profit_pct=float(item.get("net_profit_pct", 0.0)),
                net_profit_usd=float(item.get("net_profit_usd", 0.0)),
            ))
        await session.commit()
