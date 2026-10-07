from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from app.config import settings


class Base(DeclarativeBase):
    pass


# Keep module importable even in environments where optional DB dependencies have
# not been installed yet. The declared requirements install aiosqlite for runtime.
try:
    engine = create_async_engine(settings.database_url, echo=False, future=True)
    AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
except ModuleNotFoundError as exc:
    if exc.name != "aiosqlite":
        raise
    engine = None
    AsyncSessionLocal = None


async def init_db() -> None:
    if engine is None:
        raise RuntimeError("Database driver is unavailable. Install dependencies from app/requirements.txt.")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_db():
    if AsyncSessionLocal is None:
        raise RuntimeError("Database driver is unavailable. Install dependencies from app/requirements.txt.")
    async with AsyncSessionLocal() as session:
        yield session
