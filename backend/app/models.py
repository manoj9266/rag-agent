from pydantic import BaseModel, EmailStr, Field


# ── Auth ──────────────────────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    company_name: str
    email: EmailStr
    password: str = Field(min_length=8)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class AuthResponse(BaseModel):
    tenant_id: str
    name: str
    api_key: str
    access_token: str
    token_type: str = "bearer"


# ── Chat ──────────────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    session_id: str | None = None
    message: str


class Source(BaseModel):
    file: str  # raw filename — for the dashboard/operator to identify the document
    title: str  # human-friendly title — safe to show end users on the widget
    page: int | None = None
    score: float | None = None  # normalized relevance score (0–1), highest first


class ChatResponse(BaseModel):
    session_id: str
    answer: str
    sources: list[Source]
    tools_used: list[str]


# ── Health ────────────────────────────────────────────────────────────────────

class HealthResponse(BaseModel):
    status: str
    index_ready: bool
    doc_count: int
    uptime_seconds: float
    embedding_backend: str
    embedding_model: str


# ── Documents ─────────────────────────────────────────────────────────────────

class IngestResponse(BaseModel):
    status: str
    filename: str
    message: str


class DocumentInfo(BaseModel):
    filename: str
    size_bytes: int
    uploaded_at: str
    updated_at: str | None
    chunk_count: int | None


class DocumentListResponse(BaseModel):
    documents: list[DocumentInfo]
    total: int


# ── Tenant ────────────────────────────────────────────────────────────────────

class TenantInfo(BaseModel):
    tenant_id: str
    name: str


# ── Admin ─────────────────────────────────────────────────────────────────────

class TenantSummary(BaseModel):
    tenant_id: str
    name: str
    email: str
    api_key_prefix: str
    created_at: str


class TenantEmbeddingRequest(BaseModel):
    backend: str  # "huggingface" or "gemini"
    model: str    # e.g. "sentence-transformers/all-MiniLM-L6-v2" or "models/gemini-embedding-001"


class TenantEmbeddingStatus(BaseModel):
    tenant_id: str
    current_backend: str
    current_model: str
    next_rebuild_backend: str
    next_rebuild_model: str
    override_set: bool
