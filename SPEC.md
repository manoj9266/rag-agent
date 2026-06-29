# Project Spec: RAG Agent — Virtual Assistant for XYZ Clients

---

## 1. Overview

**Product**: Production-grade RAG-powered virtual assistant  
**Builder**: XYZ  
**Consumers**: Enterprise clients who embed it into their websites  
**Stack**: Next.js 14 + FastAPI + Google Gemini + FAISS → pgvector + PostgreSQL + Redis + GitHub Actions

The system answers questions from client-provided documents and calls registered API tools for live data. It is deployed as a REST API with an embeddable JS widget for zero-effort client integration.

**Multi-tenancy model**: A single deployment serves multiple clients (tenants). Each tenant self-registers and receives a unique API key. All data — documents, vectors, sessions — is fully isolated per tenant. One API key = one tenant = one isolated knowledge base.

---

## 2. System Architecture

```
┌─────────────────────────────────────────────────────────┐
│                     Client's Website                     │
│   <script src="widget.js" data-api-key="..."></script>   │
└───────────────────┬─────────────────────────────────────┘
                    │ POST /v1/chat (HTTPS + API Key)
┌───────────────────▼─────────────────────────────────────┐
│                    FastAPI Application                    │
│                                                          │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────────┐  │
│  │ Auth Layer  │  │ Rate Limiter │  │ Request Logger │  │
│  │ (→ Tenant) │  │ (per tenant) │  │ (+tenant_id)   │  │
│  └──────┬──────┘  └──────┬───────┘  └───────┬────────┘  │
│         └────────────────┴──────────────────┘            │
│                          │ tenant_id                     │
│              ┌───────────▼──────────┐                   │
│              │    Session Manager   │                   │
│              │  (Redis, per tenant) │                   │
│              └───────────┬──────────┘                   │
│                          │ history                      │
│              ┌───────────▼──────────┐                   │
│              │   LangChain Agent    │                   │
│              │   (ReAct pattern)    │                   │
│              └──┬──────────────┬───┘                   │
│                 │              │                         │
│    ┌────────────▼───┐  ┌───────▼──────────┐            │
│    │ search_docs()  │  │  API Tools        │            │
│    │                │  │  get_product()    │            │
│    │  VectorStore   │  │  get_order()      │            │
│    │ (per tenant)   │  └───────────────────┘            │
│    └────────────────┘                                   │
│                                                          │
│  ┌──────────────────┐   ┌───────────────────────┐       │
│  │   PostgreSQL     │   │  Google Gemini 2.5    │       │
│  │ (Supabase)       │   │  Flash (LLM)          │       │
│  │ tenants +        │   └───────────────────────┘       │
│  │ documents +      │                                    │
│  │ chunks (Phase 2) │                                    │
│  └──────────────────┘                                   │
└─────────────────────────────────────────────────────────┘
```

---

## 3. Project Structure

```
rag_agent/
├── frontend/                        # Next.js 14 App Router
│   ├── app/
│   │   ├── (auth)/
│   │   │   ├── register/page.tsx
│   │   │   └── login/page.tsx
│   │   ├── dashboard/page.tsx       # Chat + Documents tabs
│   │   └── layout.tsx
│   ├── components/
│   │   ├── ui/                      # shadcn/ui primitives
│   │   ├── ChatPanel.tsx
│   │   ├── DocumentsPanel.tsx
│   │   └── UploadZone.tsx
│   ├── lib/
│   │   └── api.ts                   # Typed fetch wrappers for all /v1/* endpoints
│   ├── next.config.ts
│   ├── tailwind.config.ts
│   ├── tsconfig.json
│   └── package.json
├── backend/                         # FastAPI backend
│   ├── app/                         # Python package
│   │   ├── main.py
│   │   ├── config.py                # Pydantic Settings
│   │   ├── models.py                # Pydantic request/response schemas
│   │   ├── database.py              # SQLAlchemy async + Supabase PostgreSQL
│   │   ├── vector_store.py          # VectorStore Protocol + FAISS/pgvector/Pinecone/Qdrant
│   │   ├── agent.py                 # LangChain ReAct AgentExecutor
│   │   ├── ingest.py                # Document loading, chunking, vector store pipeline
│   │   ├── tools.py                 # @tool: search_documents, get_product_info, get_order_status
│   │   ├── session.py               # Redis-backed session store (tenant-scoped)
│   │   ├── auth.py                  # JWT + API key → Tenant dependency
│   │   └── logger.py                # JSON structured logging
│   ├── tests/
│   │   ├── conftest.py              # Fixtures: test client, sample docs, mock LLM, two tenants
│   │   ├── test_api.py
│   │   ├── test_ingest.py
│   │   ├── test_auth.py
│   │   └── test_tenants.py
│   ├── scripts/
│   │   ├── migrate_to_pgvector.py
│   │   ├── migrate_to_pinecone.py
│   │   └── migrate_to_qdrant.py
│   ├── requirements.txt
│   └── Dockerfile
├── static/
│   └── widget.js                    # Vanilla JS embeddable widget (unchanged)
├── input_docs/
│   └── {tenant_id}/                 # Per-tenant docs (volume-mounted)
├── faiss_index/
│   └── {tenant_id}/                 # Per-tenant FAISS index (Phase 1 only)
├── nginx/
│   └── nginx.conf                   # Reverse proxy config for GCP VM
├── .github/
│   └── workflows/
│       ├── ci.yml                   # Lint + test on every PR
│       └── deploy-gcp.yml           # SSH deploy to GCP VM on push to main
├── docker-compose.yml               # Local dev (postgres + redis + app)
├── docker-compose.prod.yml          # GCP VM production (nginx + postgres + redis + app)
├── .env.example
└── README.md                        # Architecture diagram, live URL, setup guide
```

---

## 4. Configuration

All config via `backend/app/config.py` (Pydantic Settings).

| Env Var | Type | Required | Default | Description |
|---------|------|----------|---------|-------------|
| `GEMINI_API_KEY` | str | Yes | — | Google Gemini API key |
| `DATABASE_URL` | str | Yes | — | PostgreSQL connection string (Supabase or local) |
| `REDIS_URL` | str | Yes | — | Redis connection string (Upstash or local) |
| `JWT_SECRET_KEY` | str | Yes | — | Secret for signing JWT tokens |
| `JWT_EXPIRE_HOURS` | int | No | `24` | JWT access token expiry |
| `ADMIN_KEY` | str | Yes | — | Operator key for admin endpoints |
| `VECTOR_BACKEND` | str | No | `"faiss"` | `"faiss"` \| `"pgvector"` \| `"pinecone"` \| `"qdrant"` |
| `PINECONE_API_KEY` | str | Phase 2B | — | Pinecone only |
| `PINECONE_INDEX_NAME` | str | Phase 2B | `"rag-agent"` | Pinecone only |
| `QDRANT_URL` | str | Phase 2C | `"http://localhost:6333"` | Qdrant only |
| `QDRANT_COLLECTION` | str | Phase 2C | `"rag-agent"` | Qdrant only |
| `ALLOWED_ORIGINS` | str | No | `"*"` | Comma-separated CORS origins |
| `FAISS_INDEX_PATH` | str | No | `"faiss_index"` | Base path for per-tenant FAISS indexes |
| `INPUT_DOCS_PATH` | str | No | `"input_docs"` | Base path for per-tenant document folders |
| `CHUNK_SIZE` | int | No | `1000` | Document chunk size (chars) |
| `CHUNK_OVERLAP` | int | No | `200` | Chunk overlap (chars) |
| `TOP_K_RESULTS` | int | No | `5` | Chunks retrieved per query |
| `SESSION_TTL_SECONDS` | int | No | `1800` | Session expiry in Redis |
| `RATE_LIMIT` | str | No | `"30/minute"` | SlowAPI rate limit per API key |
| `LOG_LEVEL` | str | No | `"INFO"` | Logging level |
| `LLM_MODEL` | str | No | `"gemini-2.5-flash"` | Gemini model name |
| `EMBEDDING_MODEL` | str | No | `"models/gemini-embedding-001"` | Embedding model |

---

## 5. Database Schema (PostgreSQL / Supabase)

```sql
-- Phase 1 tables (always required)
CREATE TABLE tenants (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id     VARCHAR(100) UNIQUE NOT NULL,
    name          VARCHAR(255) NOT NULL,
    email         VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    api_key       VARCHAR(255) UNIQUE NOT NULL,
    created_at    TIMESTAMPTZ DEFAULT NOW(),
    updated_at    TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE documents (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id   VARCHAR(100) NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
    filename    VARCHAR(255) NOT NULL,
    size_bytes  INTEGER NOT NULL,
    chunk_count INTEGER,                 -- NULL while indexing
    uploaded_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at  TIMESTAMPTZ,
    UNIQUE(tenant_id, filename)
);

-- Phase 2 table (pgvector option — run after enabling extension)
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE chunks (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id   VARCHAR(100) NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
    filename    VARCHAR(255) NOT NULL,
    chunk_index INTEGER NOT NULL,
    content     TEXT NOT NULL,
    embedding   vector(768),             -- gemini-embedding-001 = 768 dimensions
    metadata    JSONB,                   -- {page, source_path}
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(tenant_id, filename, chunk_index)
);

CREATE INDEX ON chunks USING hnsw (embedding vector_cosine_ops);
```

---

## 5b. Pydantic Data Models (`backend/app/models.py`)

```python
# Auth
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
    api_key: str          # Full key — shown at register/login only
    access_token: str     # JWT — used for dashboard API calls
    token_type: str = "bearer"

# Chat
class ChatRequest(BaseModel):
    session_id: str | None = None
    message: str

class Source(BaseModel):
    file: str
    page: int | None

class ChatResponse(BaseModel):
    session_id: str
    answer: str
    sources: list[Source]
    tools_used: list[str]

# Health
class HealthResponse(BaseModel):
    status: str           # "ok" | "degraded"
    index_ready: bool
    doc_count: int
    uptime_seconds: float

# Documents
class IngestResponse(BaseModel):
    status: str           # "accepted"
    filename: str
    message: str

class DocumentInfo(BaseModel):
    filename: str
    size_bytes: int
    uploaded_at: str      # ISO 8601
    updated_at: str | None
    chunk_count: int | None   # None while indexing

class DocumentListResponse(BaseModel):
    documents: list[DocumentInfo]
    total: int

# Tenant
class TenantInfo(BaseModel):
    tenant_id: str
    name: str
```

---

## 6. API Specification

Base URL: `https://<host>/v1`

Auth on `/v1/*` endpoints: either `Authorization: Bearer <jwt>` (dashboard) or `X-API-Key: <api_key>` (widget) — both resolve to a `Tenant`.

### Public Auth Endpoints (no auth required)

| Endpoint | Purpose | Response |
|----------|---------|----------|
| `POST /v1/auth/register` | Self-service tenant registration | `201 AuthResponse` |
| `POST /v1/auth/login` | Login + retrieve API key | `200 AuthResponse` |
| `GET /register` | Serve Next.js SPA | `index.html` |
| `GET /login` | Serve Next.js SPA | `index.html` |
| `GET /dashboard` | Serve Next.js SPA (protected client-side) | `index.html` |

Rate limit on auth endpoints: `5 req/min per IP`.

### Tenant Endpoints (auth required)

| Endpoint | Purpose | Response |
|----------|---------|----------|
| `GET /v1/tenant` | Return authenticated tenant info | `200 TenantInfo` |

### Chat Endpoints

| Endpoint | Purpose | Response |
|----------|---------|----------|
| `POST /v1/chat` | Send message to agent | `200 ChatResponse` |
| `POST /v1/chat/stream` | SSE streaming version | `text/event-stream` (events: `token`, `sources`, `done`) |
| `DELETE /v1/session/{session_id}` | Clear session history | `204` |

### Document Endpoints

| Endpoint | Purpose | Response |
|----------|---------|----------|
| `POST /v1/ingest` | Upload new document | `202 IngestResponse` |
| `GET /v1/documents` | List tenant documents | `200 DocumentListResponse` |
| `PUT /v1/documents/{filename}` | Replace existing document | `202 IngestResponse` |
| `DELETE /v1/documents/{filename}` | Delete document | `202 IngestResponse` |

**Accepted file types**: `.pdf`, `.txt`, `.docx`, `.md`  
**Errors**: `400` unsupported type, `409` duplicate filename (POST only), `404` not found (PUT/DELETE)

### Health

| Endpoint | Purpose | Response |
|----------|---------|----------|
| `GET /v1/health` | Health check | `200 HealthResponse` |

### Admin Endpoints (`X-Admin-Key` header required)

| Endpoint | Purpose | Response |
|----------|---------|----------|
| `GET /admin/tenants` | List all tenants (key prefixes only) | `200 list[TenantSummary]` |
| `DELETE /admin/tenants/{tenant_id}` | Remove a tenant | `204` |
| `POST /admin/tenants/{tenant_id}/rotate-key` | Rotate API key | `200 AuthResponse` |

---

## 7. Component Specifications

### 7.1 `backend/app/auth.py` — Auth Dependencies

```python
# Dashboard calls use JWT
async def get_tenant_from_jwt(token: str = Depends(oauth2_scheme)) -> Tenant

# Widget calls use API key
async def get_tenant_from_api_key(x_api_key: str = Header(...)) -> Tenant

# Tries JWT first, falls back to API key
async def get_tenant(...) -> Tenant
```

### 7.2 `backend/app/vector_store.py` — VectorStore Abstraction

```python
class VectorStore(Protocol):
    def add_documents(self, tenant_id: str, filename: str, chunks: list[Document]) -> int
    def update_documents(self, tenant_id: str, filename: str, chunks: list[Document]) -> int
    def delete_documents(self, tenant_id: str, filename: str) -> None
    def search(self, tenant_id: str, query: str, top_k: int) -> list[Document]
    def is_ready(self, tenant_id: str) -> bool

class FAISSVectorStore:      # Phase 1 — full rebuild, local files
class PGVectorStore:         # Phase 2A — per-doc SQL ops via DATABASE_URL
class PineconeVectorStore:   # Phase 2B — per-doc ops, managed cloud
class QdrantVectorStore:     # Phase 2C — per-doc ops, self-hosted Docker

def get_vector_store(settings) -> VectorStore:
    match settings.VECTOR_BACKEND:
        case "pgvector":  return PGVectorStore(settings)
        case "pinecone":  return PineconeVectorStore(settings)
        case "qdrant":    return QdrantVectorStore(settings)
        case _:           return FAISSVectorStore(settings)
```

Injected as a FastAPI dependency on all document + chat routes.

### 7.3 `backend/app/ingest.py` — Ingest Pipeline

```
load_documents(path) → list[Document]
  ├── PyPDFLoader      for .pdf
  ├── TextLoader       for .txt, .md
  └── Docx2txtLoader   for .docx

chunk_documents(docs) → list[Document]
  └── RecursiveCharacterTextSplitter(chunk_size, chunk_overlap)

# Phase 1 (FAISS) — full rebuild
run_ingest(tenant_id, vector_store, db) → None
  # Loads all files from INPUT_DOCS_PATH/{tenant_id}/
  # Rebuilds entire index, updates chunk_count in documents table

# Phase 2 (pgvector / Pinecone / Qdrant) — per-document
add_or_update_document(tenant_id, filename, vector_store, db) → None
  # Loads + chunks single file
  # Calls vector_store.update_documents() — upserts new, deletes old vectors
  # Updates chunk_count for that filename only

delete_document(tenant_id, filename, vector_store, db) → None
  # Calls vector_store.delete_documents()
  # Deletes row from documents table
```

### 7.4 `backend/app/session.py` — Redis Session Store

- Key pattern: `session:{tenant_id}:{session_id}` — tenant isolation built-in
- TTL via Redis `EXPIRE` on every write
- New session: generate UUID; bare UUID returned to client (prefix is internal)

### 7.5 `backend/app/agent.py` — ReAct Agent

```
build_agent(tools, llm) → AgentExecutor
  └── create_react_agent(llm, tools, prompt)
      └── System prompt: "Answer ONLY from provided context.
                          If unsure, say you don't know.
                          Always cite your source."

run_agent(agent, message, history) → {answer, sources, tools_used}
```

### 7.6 `backend/app/tools.py` — Agent Tools

```python
@tool
def search_documents(query: str) -> str:
    """Search the knowledge base for relevant information."""
    # Calls vector_store.search(tenant_id, query, top_k)

@tool
def get_product_info(product_id: str) -> str:
    """Get product details from the product catalog."""
    # Mock: returns product name, price, description from dict

@tool
def get_order_status(order_id: str) -> str:
    """Get the current status of a customer order."""
    # Mock: returns order status, estimated delivery from dict
```

### 7.7 `backend/app/logger.py` — Structured Logging

JSON log lines per request: `request_id`, `tenant_id`, `method`, `path`, `session_id`, `latency_ms`, `status_code`, `tools_used`

---

## 8. Frontend (Next.js 14)

### Pages

**`/register`** — `Register.jsx`
- Fields: Company Name, Email, Password, Confirm Password
- `POST /v1/auth/register` → on success show API key with copy button + "Save this key" warning
- Link to `/login`

**`/login`** — `Login.jsx`
- Fields: Email, Password
- `POST /v1/auth/login` → store `access_token` in httpOnly cookie → redirect to `/dashboard`

**`/dashboard`** — `Dashboard.jsx`
- Protected: redirects to `/login` if no token
- Header: tenant name + Copy API Key + Logout
- **Chat tab** (`ChatPanel.tsx`): message input, conversation history, inline source citations
- **Documents tab** (`DocumentsPanel.tsx`):
  - `UploadZone.tsx`: drag-and-drop / file picker → `POST /v1/ingest`
  - Document list: Filename, Size, Uploaded, Chunks (`"indexing..."` while null)
  - Per-row: Replace (`PUT`) + Delete (confirm modal → `DELETE`)
  - Auto-polls `GET /v1/documents` every 3s while any `chunk_count` is null

### `frontend/lib/api.ts`
Typed fetch wrappers for all backend endpoints. Reads JWT from cookie or session store.

---

## 9. JS Widget (`static/widget.js`)

Vanilla JS — must be framework-agnostic (embeds on any client website).

| Attribute | Required | Default | Description |
|-----------|----------|---------|-------------|
| `data-api-key` | Yes | — | Client's API key |
| `data-api-url` | No | `/v1/chat` | Chat endpoint URL |
| `data-title` | No | `"Assistant"` | Widget header title |
| `data-placeholder` | No | `"Ask me anything..."` | Input placeholder |
| `data-theme` | No | `"light"` | `"light"` or `"dark"` |
| `data-position` | No | `"bottom-right"` | `"bottom-right"` or `"bottom-left"` |

```html
<script src="https://your-domain.com/static/widget.js"
        data-api-key="your-client-api-key"
        data-title="Acme Support"
        data-theme="light">
</script>
```

---

## 10. Docker & Deployment

### Local Dev (`docker-compose.yml`)
```yaml
services:
  app:
    build: ./backend
    ports: ["8000:8000"]
    env_file: .env
    volumes:
      - ./input_docs:/app/input_docs
      - ./faiss_index:/app/faiss_index
  postgres:
    image: postgres:16
    environment: { POSTGRES_DB: ragagent, POSTGRES_PASSWORD: secret }
  redis:
    image: redis:7-alpine
```

### Production — Option A: Railway
1. Connect GitHub repo → Railway detects `backend/Dockerfile`
2. Add Railway PostgreSQL plugin → `DATABASE_URL` auto-set
3. Add Upstash Redis → set `REDIS_URL` manually
4. Set remaining env vars in Railway dashboard
5. Connect Vercel → root directory = `frontend/` → set `NEXT_PUBLIC_API_URL`
6. Push to `main` → both auto-deploy

### Production — Option B: GCP Compute Engine VM
```yaml
# docker-compose.prod.yml
services:
  nginx:
    image: nginx:alpine
    volumes: [./nginx/nginx.conf:/etc/nginx/conf.d/default.conf]
    ports: ["80:80", "443:443"]
  app:
    build: ./backend
    env_file: .env.prod
    volumes:
      - ./input_docs:/app/input_docs
      - ./faiss_index:/app/faiss_index
  postgres:
    image: postgres:16
    volumes: [pgdata:/var/lib/postgresql/data]
  redis:
    image: redis:7-alpine

volumes:
  pgdata:
```

- nginx reverse proxies `https://api.yourdomain.com` → FastAPI :8000
- SSL via certbot (Let's Encrypt)
- GitHub Actions `.github/workflows/deploy-gcp.yml` SSH-deploys on push to `main`

---

## 11. CI/CD (GitHub Actions)

**`.github/workflows/ci.yml`** — triggers on every PR:
- `ruff` lint (Python)
- `mypy` type check (Python)
- `pytest` (backend tests)
- `eslint` + `tsc --noEmit` (TypeScript)

**`.github/workflows/deploy-gcp.yml`** — triggers on push to `main`:
- SSH into GCP VM → `git pull` → `docker-compose -f docker-compose.prod.yml up -d --build`

Railway deploys automatically via GitHub integration (no workflow needed).

---

## 12. Dependencies

### Backend (`backend/requirements.txt`)
```
# AI / RAG
langchain>=0.2.0
langchain-google-genai>=1.0.0
langchain-community>=0.2.0
faiss-cpu>=1.8.0
pypdf>=4.0.0
python-docx>=1.1.0
docx2txt>=0.8

# API Server
fastapi>=0.110.0
uvicorn[standard]>=0.29.0
python-multipart>=0.0.9
slowapi>=0.1.9

# Database
sqlalchemy[asyncio]>=2.0.0
asyncpg>=0.29.0
redis>=5.0.0

# Auth
python-jose[cryptography]>=3.3.0
bcrypt>=4.0.0

# Config
pydantic[email]>=2.0.0
pydantic-settings>=2.0.0

# Phase 2 (install as needed)
# pinecone-client>=3.0.0
# qdrant-client>=1.9.0

# Testing
pytest>=8.0.0
pytest-asyncio>=0.23.0
httpx>=0.27.0
```

### Frontend (`frontend/package.json`)
```json
{
  "dependencies": {
    "next": "^14",
    "react": "^18",
    "react-dom": "^18",
    "lucide-react": "latest"
  },
  "devDependencies": {
    "typescript": "^5",
    "tailwindcss": "^3",
    "@types/react": "^18"
  }
}
```
Plus shadcn/ui components (`@radix-ui/react-*`) added via `npx shadcn-ui@latest add`.

---

## 13. Implementation Order

| Step | What |
|------|------|
| 1 | Repo scaffold: `.env.example`, `.gitignore`, `docker-compose.yml` |
| 2 | `backend/app/config.py` — Pydantic Settings |
| 3 | `backend/app/database.py` — SQLAlchemy + PostgreSQL (tenants + documents tables) |
| 4 | `backend/app/models.py` — Pydantic schemas |
| 5 | `backend/app/logger.py` — JSON structured logging |
| 6 | `backend/app/auth.py` — JWT + API key dependencies |
| 7 | `backend/app/vector_store.py` — VectorStore Protocol + FAISSVectorStore |
| 8 | `backend/app/session.py` — Redis-backed sessions |
| 9 | `backend/app/ingest.py` — Document pipeline (Phase 1 FAISS) |
| 10 | `backend/app/tools.py` — Agent tools |
| 11 | `backend/app/agent.py` — ReAct AgentExecutor |
| 12 | `backend/app/main.py` — All routes + middleware |
| 13 | `static/widget.js` — Vanilla JS embeddable widget |
| 14 | `backend/tests/` — pytest suite |
| 15 | `frontend/` scaffold — `npx create-next-app` + shadcn/ui init |
| 16 | `frontend/lib/api.ts` — Typed API client |
| 17 | Register + Login pages |
| 18 | Dashboard — Chat tab |
| 19 | Dashboard — Documents tab |
| 20 | `nginx/nginx.conf` + `docker-compose.prod.yml` |
| 21 | `.github/workflows/ci.yml` + `deploy-gcp.yml` |
| 22 | `README.md` — architecture diagram + live URL + badges |
| 23 | **Phase 2**: `PGVectorStore` in `vector_store.py` + `chunks` table migration |

---

## 14. Phase 1 Verification Checklist

| Test | Expected |
|------|----------|
| `docker compose up` | App starts, no errors |
| `POST /v1/auth/register` | `201` with `api_key` + `access_token` |
| `POST /v1/auth/login` — wrong password | `401` |
| `GET /v1/tenant` | Returns tenant info |
| `POST /v1/chat` — doc question | Grounded answer + source file/page |
| `POST /v1/chat` — follow-up | Context-aware, uses session history |
| `POST /v1/ingest` — `.pdf` | `202`; registry entry added |
| `POST /v1/ingest` — `.docx` | `202`; extracted via `Docx2txtLoader` |
| `POST /v1/ingest` — `.md` | `202`; extracted via `TextLoader` |
| `POST /v1/ingest` — `.doc` | `400` unsupported type |
| `POST /v1/ingest` — duplicate filename | `409 Conflict` |
| `GET /v1/documents` | Lists files with `chunk_count` once indexed |
| `DELETE /v1/documents/{filename}` | `202`; file removed, background rebuild |
| `PUT /v1/documents/{filename}` | `202`; file replaced, `updated_at` set |
| Acme uploads doc → Globex `GET /v1/documents` | Globex sees empty list |
| Chat with acme key | Only acme docs in sources (no cross-tenant leakage) |
| `/register` in browser | React form renders |
| `/dashboard` without login | Redirects to `/login` |
| Embed `widget.js` on any HTML page | Chat bubble works |
| `pytest` | All tests pass |
| `npm run build` in `frontend/` | No type errors |

---

## 15. Phase 2 — Managed Vector Store (No Full Rebuild)

### Problem with Phase 1 (FAISS)
Every add, update, or delete triggers a **full rebuild** — re-embedding all documents from scratch. With 100+ large PDFs this becomes slow and expensive (Gemini embedding API costs per token).

### Solution
Replace FAISS with a vector store that supports **per-document upsert and delete by metadata filter**. The `VectorStore` abstraction means this is a single config change — no route or agent code changes.

---

### Vector DB Options

| Option | Type | Tenant isolation | Per-doc ops | Extra service |
|--------|------|-----------------|-------------|---------------|
| **pgvector** ⭐ | PostgreSQL extension (Supabase) | `tenant_id` column | `DELETE WHERE` + `INSERT` | None — reuses `DATABASE_URL` |
| **Pinecone** | Managed cloud | Namespaces per tenant | `upsert` + `delete(filter)` | Pinecone account |
| **Qdrant** | Self-hosted Docker | Payload filter | `upsert` + `delete(filter)` | Docker container |

**Recommended: pgvector** — already in the stack (Supabase), zero extra service, one database for everything.

---

### Option A: pgvector

```
Per-document operations (plain SQL):
  ADD    → embed chunks → INSERT INTO chunks (tenant_id, filename, ...)
  UPDATE → DELETE FROM chunks WHERE tenant_id=$1 AND filename=$2
           → embed new chunks → INSERT INTO chunks ...
  DELETE → DELETE FROM chunks WHERE tenant_id=$1 AND filename=$2
  SEARCH → SELECT content, metadata FROM chunks
            WHERE tenant_id=$1
            ORDER BY embedding <=> $query_vec LIMIT top_k
```

LangChain integration:
```python
from langchain_community.vectorstores import PGVector

store = PGVector(
    connection_string=settings.DATABASE_URL,
    embedding_function=embeddings,
    collection_name=tenant_id,
)
```

### Option B: Pinecone

```
One index "rag-agent", namespace per tenant
  ADD/UPDATE → pinecone.upsert(vectors, namespace=tenant_id)
  DELETE     → pinecone.delete(filter={"filename": filename}, namespace=tenant_id)
  SEARCH     → pinecone.query(embedding, top_k, namespace=tenant_id)
```

### Option C: Qdrant (GCP VM)

```yaml
# add to docker-compose.prod.yml
services:
  qdrant:
    image: qdrant/qdrant:latest
    volumes: [qdrant_data:/qdrant/storage]
```

```
One collection "rag-agent", filter by tenant_id payload
  ADD/UPDATE → qdrant.upsert(points with tenant_id in payload)
  DELETE     → qdrant.delete(filter={"filename": f, "tenant_id": t})
  SEARCH     → qdrant.search(vec, filter={"tenant_id": t}, limit=top_k)
```

---

### Migration Path

**Option A — pgvector (simplest):**
1. Supabase SQL editor: `CREATE EXTENSION IF NOT EXISTS vector;` + `chunks` table DDL (see §5)
2. Set `VECTOR_BACKEND=pgvector` in `.env`
3. `python scripts/migrate_to_pgvector.py` — embeds all existing docs, inserts into `chunks`
4. Restart app; delete `faiss_index/`

**Option B — Pinecone:**
1. Create Pinecone index (`rag-agent`, dim `768`, cosine)
2. Set `VECTOR_BACKEND=pinecone`, `PINECONE_API_KEY`, `PINECONE_INDEX_NAME`
3. `python scripts/migrate_to_pinecone.py`
4. Restart app; delete `faiss_index/`

**Option C — Qdrant:**
1. Add Qdrant to `docker-compose.prod.yml`
2. Set `VECTOR_BACKEND=qdrant`, `QDRANT_URL`
3. `python scripts/migrate_to_qdrant.py`
4. Restart app; delete `faiss_index/`

---

### Phase 2 Verification Checklist

| Test | Expected |
|------|--------------------|
| `VECTOR_BACKEND=pgvector` — app start | App starts; `chunks` table in Supabase |
| `POST /v1/ingest` | `202`; only that doc embedded (not full rebuild) |
| `DELETE /v1/documents/{filename}` | `202`; vectors deleted in <1s, no re-embedding |
| `PUT /v1/documents/{filename}` | `202`; old vectors deleted, new chunks inserted |
| Chat after delete | Deleted doc no longer appears in answers |
| Two tenants, same filename | No cross-tenant vector contamination |
| `SELECT COUNT(*) FROM chunks WHERE tenant_id='acme'` | Returns chunk count for acme only |
| `VECTOR_BACKEND=faiss` | Falls back to Phase 1 (full rebuild) |
