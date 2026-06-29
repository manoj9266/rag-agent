# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Multi-tenant RAG-powered virtual assistant. A single FastAPI deployment serves multiple enterprise clients (tenants). Each tenant self-registers, gets a unique API key, uploads documents, and gets an isolated knowledge base. The agent answers questions from those documents and calls registered API tools.

**Stack:** FastAPI + LangChain ReAct + Google Gemini (LLM + embeddings) + FAISS (Phase 1) / pgvector (Phase 2) + PostgreSQL (Supabase) + Redis + Next.js 14

**Implementation status:** See `PROGRESS.md`. Phase 1 (Steps 1–22) is complete: backend, embeddable widget, pytest suite, Next.js frontend, infra, and docs. Only Phase 2 (Step 23 — `PGVectorStore` + `chunks` migration) is pending. Production deploys to Railway (backend) + Vercel (frontend) with Neon Postgres and Upstash Redis.

## Commands

### Backend (run from `backend/`)

```bash
# Install deps
pip install -r requirements.txt

# Run dev server
uvicorn app.main:app --reload --port 8000

# Run all tests
pytest

# Run a single test file
pytest tests/test_api.py -v

# Run a single test
pytest tests/test_api.py::test_register -v

# Lint
ruff check app/

# Type check
mypy app/
```

### Docker (run from project root)

```bash
# Start full local stack (postgres + redis + app)
docker compose up

# Rebuild after code changes
docker compose up --build

# Run in background
docker compose up -d
```

### Frontend (run from `frontend/` — not yet scaffolded)

```bash
npm run dev
npm run build
npm run lint
npx tsc --noEmit
```

## Architecture

### Multi-tenancy

Every request resolves to a `Tenant` via `backend/app/auth.py:get_tenant()`. It tries JWT first (dashboard calls), then falls back to `X-API-Key` header (widget calls). The resolved `tenant.tenant_id` is the isolation key passed to every downstream call — vector store, session store, document table, file paths.

### Auth flow

- `POST /v1/auth/register` → creates `TenantRow` with bcrypt password hash + random `api_key`
- `POST /v1/auth/login` → verifies password, returns JWT (`access_token`) + `api_key`
- Dashboard uses JWT (`Authorization: Bearer`); embedded widget uses `X-API-Key`
- Admin endpoints use a separate `X-Admin-Key` header checked against `settings.ADMIN_KEY`

### Vector store abstraction

`backend/app/vector_store.py` defines a `VectorStore` Protocol. `get_vector_store(settings)` returns the right implementation based on `VECTOR_BACKEND` env var:

- `"faiss"` (default, Phase 1): per-tenant FAISS indexes saved to `faiss_index/{tenant_id}/`. **Every add/update/delete triggers a full rebuild** via `run_ingest()` — re-embeds all docs for that tenant. No per-doc ops.
- `"pgvector"` (Phase 2A): per-doc upsert/delete via `chunks` table (requires `vector` extension in Postgres).
- `"pinecone"` (Phase 2B): Pinecone namespaces per tenant.
- `"qdrant"` (Phase 2C): Qdrant payload filter per tenant.

When adding Phase 2 support, only `vector_store.py` changes — no route or agent code changes needed.

### Document lifecycle (Phase 1 / FAISS)

1. `POST /v1/ingest` → save file to `input_docs/{tenant_id}/`, insert `DocumentRow` with `chunk_count=None`
2. Background task calls `run_ingest()` → loads all files for tenant, chunks, rebuilds FAISS index, updates `chunk_count`
3. Frontend polls `GET /v1/documents` every 3s until no `chunk_count` is null

### Agent pipeline

`backend/app/agent.py` builds a LangChain ReAct `AgentExecutor`. Per request in `POST /v1/chat`:
1. Load session history from Redis (`session:{tenant_id}:{session_id}`)
2. Build tools: `make_search_tool(vector_store, tenant_id, top_k)` + `get_product_info` + `get_order_status`
3. `run_agent()` invokes the executor, extracts sources from `intermediate_steps`, appends turn to history, saves back to Redis

`make_search_tool()` in `tools.py` is a closure — it binds `tenant_id` into the tool so the agent cannot search another tenant's data.

### Session isolation

Redis key pattern: `session:{tenant_id}:{session_id}`. The `session_id` returned to clients is a bare UUID; the tenant prefix is internal. TTL is reset on every write (`SESSION_TTL_SECONDS`, default 30 min).

### Database

`backend/app/database.py` uses SQLAlchemy async with `asyncpg`. ORM models (`TenantRow`, `DocumentRow`) live in the same file as the engine/session. `create_tables()` is called at startup via FastAPI lifespan. The `chunks` table (for pgvector) is defined in SQL in `SPEC.md §5` — not yet in the ORM (add it when implementing Phase 2).

### Config

All config via `backend/app/config.py` (Pydantic Settings, reads `.env`). Access as `from app.config import settings`. The `VECTOR_BACKEND` env var is the switch for Phase 1 → Phase 2 migration with zero code changes.

## Key constraints

- **Tenant isolation is enforced in application code**, not at the DB level. Every query and vector search must include `tenant_id`. Never pass unchecked user input as `tenant_id`.
- `FAISSVectorStore.add_documents()` / `update_documents()` / `delete_documents()` raise `NotImplementedError` — callers must check `isinstance(vector_store, FAISSVectorStore)` and use `rebuild()` / `run_ingest()` instead (already done in `main.py`).
- Accepted file types: `.pdf`, `.txt`, `.docx`, `.md` — enforced in `ingest.py:SUPPORTED_EXTENSIONS` and validated in `POST /v1/ingest`.
- `DATABASE_URL` must use `+asyncpg` driver for async SQLAlchemy. PGVector sync calls strip it with `.replace("+asyncpg", "")`.
