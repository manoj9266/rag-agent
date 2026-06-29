from datetime import datetime
from urllib.parse import urlsplit, urlunsplit

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.config import settings


def _build_engine():
    """Create the async engine, adding asyncpg/Neon-specific args only for Postgres.

    Neon (and most managed Postgres) require TLS, and asyncpg trips over libpq-only
    query params (sslmode, channel_binding) plus prepared-statement caching when going
    through a pooler. We strip those params and pass ssl/statement_cache_size via
    connect_args. SQLite (used in CI/tests) gets none of this.
    """
    url = settings.DATABASE_URL
    if "asyncpg" not in url:
        return create_async_engine(url, echo=False)

    # asyncpg.connect() rejects libpq keywords; drop them from the query string.
    parts = urlsplit(url)
    kept = [
        kv
        for kv in parts.query.split("&")
        if kv and kv.split("=", 1)[0] not in {"sslmode", "channel_binding"}
    ]
    clean_url = urlunsplit(parts._replace(query="&".join(kept)))

    return create_async_engine(
        clean_url,
        echo=False,
        pool_pre_ping=True,  # drop stale conns after Neon compute auto-suspend
        connect_args={"ssl": True, "statement_cache_size": 0},
    )


engine = _build_engine()
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session


async def create_tables() -> None:
    """Create all tables on startup (idempotent)."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


# ── ORM Models ────────────────────────────────────────────────────────────────


class TenantRow(Base):
    __tablename__ = "tenants"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    api_key: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class DocumentRow(Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(100), ForeignKey("tenants.tenant_id", ondelete="CASCADE"), nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
