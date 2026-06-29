"""
Shared fixtures for the test suite.

Uses an in-memory SQLite database so tests run without a real Postgres instance.
LLM and embedding calls are mocked so tests never hit the Gemini API.
"""
import os
import tempfile
import uuid
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# ── Env vars must be set before importing app modules ─────────────────────────
os.environ.setdefault("GEMINI_API_KEY", "test-key")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-pytest-only")
os.environ.setdefault("ADMIN_KEY", "test-admin-key")
os.environ.setdefault("VECTOR_BACKEND", "faiss")

from app.database import Base, DocumentRow, TenantRow
from app.auth import create_access_token, hash_password
from app.main import app
from app.vector_store import FAISSVectorStore


# ── In-memory DB engine ───────────────────────────────────────────────────────

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"

@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"


@pytest_asyncio.fixture(scope="function")
async def db_engine():
    engine = create_async_engine(TEST_DB_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def db_session(db_engine) -> AsyncGenerator[AsyncSession, None]:
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session


# ── Mock Redis ────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def mock_redis():
    store = {}

    async def fake_get(key):
        return store.get(key)

    async def fake_set(key, val, **kwargs):
        store[key] = val

    async def fake_delete(key):
        store.pop(key, None)

    async def fake_expire(key, ttl):
        pass

    mock = MagicMock()
    mock.get = fake_get
    mock.set = fake_set
    mock.delete = fake_delete
    mock.expire = fake_expire

    with patch("app.session.get_redis", return_value=mock):
        yield mock


# ── Mock vector store ─────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def mock_vector_store():
    mock = MagicMock(spec=FAISSVectorStore)
    mock.search.return_value = []
    mock.is_ready.return_value = True
    mock.rebuild.return_value = None

    with patch("app.main.vector_store", mock), \
         patch("app.main.get_vector_store", return_value=mock):
        yield mock


# ── Mock LLM agent ────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def mock_agent():
    fake_result = {
        "answer": "This is a mocked answer.",
        "sources": [],
        "tools_used": [],
    }
    with patch("app.main.build_agent") as mock_build, \
         patch("app.main.run_agent", return_value=fake_result) as mock_run:
        mock_executor = MagicMock()
        mock_build.return_value = mock_executor
        yield {"build": mock_build, "run": mock_run, "result": fake_result}


# ── DB override in FastAPI ─────────────────────────────────────────────────────

@pytest_asyncio.fixture(scope="function")
async def client(db_engine) -> AsyncGenerator[AsyncClient, None]:
    from app.database import get_db
    from app.main import app

    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)

    async def override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    # Patch background ingest tasks so they don't hit the real DB or real vector store
    with patch("app.auth.AsyncSessionLocal", session_factory), \
         patch("app.database.engine", db_engine), \
         patch("app.main._trigger_rebuild"), \
         patch("app.main.add_or_update_document"), \
         patch("app.main.delete_document"):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as ac:
            yield ac

    app.dependency_overrides.clear()


# ── Tenant fixtures ────────────────────────────────────────────────────────────

@pytest_asyncio.fixture(scope="function")
async def tenant_acme(db_session: AsyncSession):
    tenant_id = "acme-" + str(uuid.uuid4())[:8]
    api_key = "sk-acme-" + str(uuid.uuid4()).replace("-", "")
    row = TenantRow(
        id=str(uuid.uuid4()),
        tenant_id=tenant_id,
        name="Acme Corp",
        email=f"acme-{uuid.uuid4().hex[:4]}@test.com",
        password_hash=hash_password("password123"),
        api_key=api_key,
    )
    db_session.add(row)
    await db_session.commit()
    return {
        "row": row,
        "tenant_id": tenant_id,
        "api_key": api_key,
        "token": create_access_token(tenant_id),
    }


@pytest_asyncio.fixture(scope="function")
async def tenant_globex(db_session: AsyncSession):
    tenant_id = "globex-" + str(uuid.uuid4())[:8]
    api_key = "sk-globex-" + str(uuid.uuid4()).replace("-", "")
    row = TenantRow(
        id=str(uuid.uuid4()),
        tenant_id=tenant_id,
        name="Globex Inc",
        email=f"globex-{uuid.uuid4().hex[:4]}@test.com",
        password_hash=hash_password("securepass"),
        api_key=api_key,
    )
    db_session.add(row)
    await db_session.commit()
    return {
        "row": row,
        "tenant_id": tenant_id,
        "api_key": api_key,
        "token": create_access_token(tenant_id),
    }


# ── Sample document fixture ───────────────────────────────────────────────────

@pytest.fixture(scope="function")
def sample_txt_file():
    content = b"This is a sample document about our product catalog."
    with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
        f.write(content)
        path = f.name
    yield path, content, "sample.txt"
    os.unlink(path)
