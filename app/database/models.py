from sqlalchemy import Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.database.database import Base


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[float] = mapped_column(Float)


class AuthSession(Base):
    __tablename__ = "auth_sessions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    created_at: Mapped[float] = mapped_column(Float)
    expires_at: Mapped[float] = mapped_column(Float)


class ScanSnapshot(Base):
    __tablename__ = "scan_snapshots"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[float] = mapped_column(Float, index=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    books_available: Mapped[int] = mapped_column(Integer, default=0)
    evaluated_routes: Mapped[int] = mapped_column(Integer, default=0)
    positive_opportunities: Mapped[int] = mapped_column(Integer, default=0)
    errors: Mapped[int] = mapped_column(Integer, default=0)
    max_gross_profit_pct: Mapped[float] = mapped_column(Float, default=0.0)
    max_net_profit_pct: Mapped[float] = mapped_column(Float, default=0.0)
    diagnostics_json: Mapped[str] = mapped_column(Text, default="{}")


class OpportunityHistory(Base):
    __tablename__ = "opportunity_history"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[float] = mapped_column(Float, index=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    buy_exchange: Mapped[str] = mapped_column(String(32))
    sell_exchange: Mapped[str] = mapped_column(String(32))
    buy_price: Mapped[float] = mapped_column(Float)
    sell_price: Mapped[float] = mapped_column(Float)
    position_size: Mapped[float] = mapped_column(Float)
    gross_profit_pct: Mapped[float] = mapped_column(Float)
    net_profit_pct: Mapped[float] = mapped_column(Float)
    net_profit_usd: Mapped[float] = mapped_column(Float)


class EngineEvent(Base):
    __tablename__ = "engine_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[float] = mapped_column(Float, index=True)
    level: Mapped[str] = mapped_column(String(16), default="INFO")
    event: Mapped[str] = mapped_column(String(80), index=True)
    message: Mapped[str] = mapped_column(Text, default="")


class AppSetting(Base):
    __tablename__ = "app_settings"
    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[str] = mapped_column(Text)
