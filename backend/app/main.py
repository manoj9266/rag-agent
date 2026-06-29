import os
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import BackgroundTasks, Depends, FastAPI, File, Header, HTTPException, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from google.genai.errors import ServerError
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent import build_agent, run_agent
from app.auth import create_access_token, get_tenant, hash_password, require_admin, verify_password
from app.config import settings
from app.database import DocumentRow, TenantRow, create_tables, get_db
from app.ingest import SUPPORTED_EXTENSIONS, add_or_update_document, chunk_documents, delete_document, load_documents, run_ingest
from app.logger import RequestLogMiddleware
from app.models import (
    AuthResponse,
    ChatRequest,
    ChatResponse,
    DocumentInfo,
    DocumentListResponse,
    HealthResponse,
    IngestResponse,
    LoginRequest,
    RegisterRequest,
    Source,
    TenantEmbeddingRequest,
    TenantEmbeddingStatus,
    TenantInfo,
    TenantSummary,
)
from app.session import delete_session, get_history, new_session_id, save_history
from app.tools import get_order_status, get_product_info, make_search_tool
from app.vector_store import FAISSVectorStore, get_vector_store

_START_TIME = time.time()

limiter = Limiter(key_func=get_remote_address)
vector_store = get_vector_store(settings)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await create_tables()
    yield


app = FastAPI(title="RAG Agent API", version="1.0.0", lifespan=lifespan)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(RequestLogMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/v1/health", response_model=HealthResponse)
async def health(db: AsyncSession = Depends(get_db)):
    count_result = await db.execute(select(func.count()).select_from(DocumentRow))
    doc_count = count_result.scalar_one()
    if settings.EMBEDDING_BACKEND == "gemini":
        emb_model = settings.EMBEDDING_MODEL
    else:
        emb_model = settings.HF_EMBEDDING_MODEL
    return HealthResponse(
        status="ok",
        index_ready=True,
        doc_count=doc_count,
        uptime_seconds=round(time.time() - _START_TIME, 2),
        embedding_backend=settings.EMBEDDING_BACKEND,
        embedding_model=emb_model,
    )


# ── Auth ──────────────────────────────────────────────────────────────────────

@app.post("/v1/auth/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
async def register(req: RegisterRequest, db: AsyncSession = Depends(get_db)):
    existing = await db.execute(select(TenantRow).where(TenantRow.email == req.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    tenant_id = req.company_name.lower().replace(" ", "-") + "-" + str(uuid.uuid4())[:8]
    api_key = "sk-" + str(uuid.uuid4()).replace("-", "")
    row = TenantRow(
        id=str(uuid.uuid4()),
        tenant_id=tenant_id,
        name=req.company_name,
        email=req.email,
        password_hash=hash_password(req.password),
        api_key=api_key,
    )
    db.add(row)
    await db.commit()

    return AuthResponse(
        tenant_id=tenant_id,
        name=req.company_name,
        api_key=api_key,
        access_token=create_access_token(tenant_id),
    )


@app.post("/v1/auth/login", response_model=AuthResponse)
async def login(req: LoginRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(TenantRow).where(TenantRow.email == req.email))
    tenant = result.scalar_one_or_none()
    if not tenant or not verify_password(req.password, tenant.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    return AuthResponse(
        tenant_id=tenant.tenant_id,
        name=tenant.name,
        api_key=tenant.api_key,
        access_token=create_access_token(tenant.tenant_id),
    )


# ── Tenant ────────────────────────────────────────────────────────────────────

@app.get("/v1/tenant", response_model=TenantInfo)
async def get_tenant_info(tenant: TenantRow = Depends(get_tenant)):
    return TenantInfo(tenant_id=tenant.tenant_id, name=tenant.name)


# ── Chat ──────────────────────────────────────────────────────────────────────

@app.post("/v1/chat", response_model=ChatResponse)
async def chat(req: ChatRequest, tenant: TenantRow = Depends(get_tenant)):
    session_id = req.session_id or new_session_id()
    history = await get_history(tenant.tenant_id, session_id)

    search_tool = make_search_tool(vector_store, tenant.tenant_id, settings.TOP_K_RESULTS)
    tools = [search_tool, get_product_info, get_order_status]
    executor = build_agent(tools)

    try:
        result = run_agent(executor, req.message, history)
    except ServerError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The assistant is temporarily unavailable due to high demand. Please try again in a moment.",
        )

    history.append({"human": req.message, "assistant": result["answer"]})
    await save_history(tenant.tenant_id, session_id, history)

    return ChatResponse(
        session_id=session_id,
        answer=result["answer"],
        sources=[Source(**s) for s in result["sources"]],
        tools_used=result["tools_used"],
    )


@app.delete("/v1/session/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def clear_session(session_id: str, tenant: TenantRow = Depends(get_tenant)):
    await delete_session(tenant.tenant_id, session_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ── Documents ─────────────────────────────────────────────────────────────────

async def _trigger_rebuild(tenant_id: str) -> None:
    """Background FAISS rebuild — only used in Phase 1."""
    from app.database import AsyncSessionLocal

    if not isinstance(vector_store, FAISSVectorStore):
        return
    async with AsyncSessionLocal() as db:
        await run_ingest(tenant_id, vector_store, db)


@app.post("/v1/ingest", response_model=IngestResponse, status_code=status.HTTP_202_ACCEPTED)
async def ingest(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    tenant: TenantRow = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unsupported file type: {ext}")

    existing = await db.execute(
        select(DocumentRow).where(
            DocumentRow.tenant_id == tenant.tenant_id,
            DocumentRow.filename == file.filename,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="File already exists. Use PUT to replace.")

    docs_dir = os.path.join(settings.INPUT_DOCS_PATH, tenant.tenant_id)
    os.makedirs(docs_dir, exist_ok=True)
    dest = os.path.join(docs_dir, file.filename)
    content = await file.read()
    with open(dest, "wb") as f:
        f.write(content)

    row = DocumentRow(
        id=str(uuid.uuid4()),
        tenant_id=tenant.tenant_id,
        filename=file.filename,
        size_bytes=len(content),
        chunk_count=None,
    )
    db.add(row)
    await db.commit()

    if isinstance(vector_store, FAISSVectorStore):
        background_tasks.add_task(_trigger_rebuild, tenant.tenant_id)
    else:
        background_tasks.add_task(add_or_update_document, tenant.tenant_id, file.filename, vector_store, db)

    return IngestResponse(status="accepted", filename=file.filename, message="File queued for indexing.")


@app.get("/v1/documents", response_model=DocumentListResponse)
async def list_documents(tenant: TenantRow = Depends(get_tenant), db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(DocumentRow).where(DocumentRow.tenant_id == tenant.tenant_id).order_by(DocumentRow.uploaded_at.desc())
    )
    rows = result.scalars().all()
    docs = [
        DocumentInfo(
            filename=r.filename,
            size_bytes=r.size_bytes,
            uploaded_at=r.uploaded_at.isoformat(),
            updated_at=r.updated_at.isoformat() if r.updated_at else None,
            chunk_count=r.chunk_count,
        )
        for r in rows
    ]
    return DocumentListResponse(documents=docs, total=len(docs))


@app.put("/v1/documents/{filename}", response_model=IngestResponse, status_code=status.HTTP_202_ACCEPTED)
async def replace_document(
    filename: str,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    tenant: TenantRow = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(DocumentRow).where(
            DocumentRow.tenant_id == tenant.tenant_id,
            DocumentRow.filename == filename,
        )
    )
    row = result.scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")

    docs_dir = os.path.join(settings.INPUT_DOCS_PATH, tenant.tenant_id)
    dest = os.path.join(docs_dir, filename)
    content = await file.read()
    with open(dest, "wb") as f:
        f.write(content)

    from datetime import datetime, timezone
    row.size_bytes = len(content)
    row.chunk_count = None
    row.updated_at = datetime.now(timezone.utc)
    await db.commit()

    if isinstance(vector_store, FAISSVectorStore):
        background_tasks.add_task(_trigger_rebuild, tenant.tenant_id)
    else:
        background_tasks.add_task(add_or_update_document, tenant.tenant_id, filename, vector_store, db)

    return IngestResponse(status="accepted", filename=filename, message="File queued for re-indexing.")


@app.delete("/v1/documents/{filename}", response_model=IngestResponse, status_code=status.HTTP_202_ACCEPTED)
async def remove_document(
    filename: str,
    background_tasks: BackgroundTasks,
    tenant: TenantRow = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(DocumentRow).where(
            DocumentRow.tenant_id == tenant.tenant_id,
            DocumentRow.filename == filename,
        )
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")

    background_tasks.add_task(delete_document, tenant.tenant_id, filename, vector_store, db)
    if isinstance(vector_store, FAISSVectorStore):
        background_tasks.add_task(_trigger_rebuild, tenant.tenant_id)

    return IngestResponse(status="accepted", filename=filename, message="File queued for deletion.")


# ── Admin ─────────────────────────────────────────────────────────────────────

@app.get("/admin/tenants", response_model=list[TenantSummary])
async def list_tenants(_: None = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(TenantRow).order_by(TenantRow.created_at.desc()))
    rows = result.scalars().all()
    return [
        TenantSummary(
            tenant_id=r.tenant_id,
            name=r.name,
            email=r.email,
            api_key_prefix=r.api_key[:12] + "...",
            created_at=r.created_at.isoformat(),
        )
        for r in rows
    ]


@app.get("/admin/tenants/{tenant_id}/embedding", response_model=TenantEmbeddingStatus)
async def get_tenant_embedding(
    tenant_id: str,
    _: None = Depends(require_admin),
):
    """Show what embedding is active now and what will be used on the tenant's next rebuild."""
    if not isinstance(vector_store, FAISSVectorStore):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only applies to FAISS backend.")
    return TenantEmbeddingStatus(tenant_id=tenant_id, **vector_store.get_tenant_embedding_status(tenant_id))


@app.put("/admin/tenants/{tenant_id}/embedding", response_model=TenantEmbeddingStatus)
async def set_tenant_embedding(
    tenant_id: str,
    req: TenantEmbeddingRequest,
    _: None = Depends(require_admin),
):
    """Pin a tenant to a specific embedding model. Takes effect on their next document upload/delete."""
    if not isinstance(vector_store, FAISSVectorStore):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only applies to FAISS backend.")
    vector_store.set_tenant_embedding(tenant_id, req.backend, req.model)
    return TenantEmbeddingStatus(tenant_id=tenant_id, **vector_store.get_tenant_embedding_status(tenant_id))


@app.delete("/admin/tenants/{tenant_id}/embedding", response_model=TenantEmbeddingStatus)
async def clear_tenant_embedding(
    tenant_id: str,
    _: None = Depends(require_admin),
):
    """Remove the per-tenant override — reverts to global EMBEDDING_BACKEND on next rebuild."""
    if not isinstance(vector_store, FAISSVectorStore):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only applies to FAISS backend.")
    vector_store.clear_tenant_embedding(tenant_id)
    return TenantEmbeddingStatus(tenant_id=tenant_id, **vector_store.get_tenant_embedding_status(tenant_id))


@app.post("/admin/reindex", status_code=status.HTTP_202_ACCEPTED)
async def admin_reindex(
    background_tasks: BackgroundTasks,
    _: None = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Rebuild all FAISS indexes. Required after changing EMBEDDING_BACKEND or HF_EMBEDDING_MODEL."""
    if not isinstance(vector_store, FAISSVectorStore):
        return {"message": "No-op: active backend is not FAISS", "queued": []}
    result = await db.execute(select(TenantRow))
    tenants = result.scalars().all()
    queued = [t.tenant_id for t in tenants]
    for tenant_id in queued:
        background_tasks.add_task(_trigger_rebuild, tenant_id)
    return {"message": f"Reindex queued for {len(queued)} tenant(s)", "queued": queued}


@app.delete("/admin/tenants/{tenant_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_tenant(
    tenant_id: str,
    _: None = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    await db.execute(delete(TenantRow).where(TenantRow.tenant_id == tenant_id))
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.post("/admin/tenants/{tenant_id}/rotate-key", response_model=AuthResponse)
async def rotate_api_key(
    tenant_id: str,
    _: None = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(TenantRow).where(TenantRow.tenant_id == tenant_id))
    tenant = result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found.")

    tenant.api_key = "sk-" + str(uuid.uuid4()).replace("-", "")
    await db.commit()

    return AuthResponse(
        tenant_id=tenant.tenant_id,
        name=tenant.name,
        api_key=tenant.api_key,
        access_token=create_access_token(tenant.tenant_id),
    )
