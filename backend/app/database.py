from datetime import datetime
from urllib.parse import urlsplit, urlunsplit

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.config import settings


def _build_engine():
    """Create the async engine, adding asyncpg-specific args only for Postgres.

    Two deployment shapes are supported:
      * Self-hosted Postgres container (no TLS) — e.g. on the GCP VM. No ssl.
      * Managed Postgres (Neon/Supabase) — requires TLS. We detect this from a
        libpq sslmode that asks for it, then pass ssl via connect_args and strip
        the libpq-only query params (sslmode, channel_binding) that asyncpg rejects.

    `statement_cache_size=0` is harmless everywhere and is needed when going through
    a transaction pooler (e.g. Neon's -pooler / PgBouncer). SQLite (CI/tests) gets none
    of this.
    """
    url = settings.DATABASE_URL
    if "asyncpg" not in url:
        return create_async_engine(url, echo=False)

    parts = urlsplit(url)
    query = dict(kv.split("=", 1) for kv in parts.query.split("&") if "=" in kv)
    # TLS only when the connection string asks for it (managed Postgres), not for a
    # plain self-hosted container which has no SSL configured.
    want_ssl = query.get("sslmode", "").lower() in {"require", "verify-ca", "verify-full"}

    # asyncpg.connect() rejects libpq keywords; drop them from the query string.
    kept = "&".join(f"{k}={v}" for k, v in query.items() if k not in {"sslmode", "channel_binding"})
    clean_url = urlunsplit(parts._replace(query=kept))

    connect_args: dict = {"statement_cache_size": 0}
    if want_ssl:
        connect_args["ssl"] = True

    return create_async_engine(
        clean_url,
        echo=False,
        pool_pre_ping=True,  # drop stale conns (managed-DB auto-suspend, idle drops)
        connect_args=connect_args,
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
