# RAG Agent — Multi-Tenant AI Virtual Assistant

A production-grade RAG-powered virtual assistant. A single FastAPI deployment serves multiple enterprise clients. Each tenant self-registers, gets an isolated knowledge base, and embeds an AI chat widget into their website.

---

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                      Client Website                          │
│  <script src="/static/widget.js" data-api-key="sk-...">      │
└─────────────────────┬────────────────────────────────────────┘
                      │ POST /v1/chat  (X-API-Key)
┌─────────────────────▼────────────────────────────────────────┐
│                   nginx (port 80/443)                        │
└─────────────────────┬────────────────────────────────────────┘
                      │
┌─────────────────────▼────────────────────────────────────────┐
│              FastAPI  (port 8000)                            │
│                                                              │
│  Auth (JWT / API Key) → Rate Limiter → Request Logger        │
│                          │ tenant_id                         │
│               ┌──────────▼──────────┐                       │
│               │   Redis Sessions    │                       │
│               └──────────┬──────────┘                       │
│                          │ history                          │
│               ┌──────────▼──────────┐                       │
│               │   LangGraph ReAct   │                       │
│               └──┬───────────────┬──┘                       │
│                  │               │                           │
│     ┌────────────▼──┐   ┌────────▼────────┐                │
│     │ search_docs() │   │  API Tools       │                │
│     │ FAISS / pgvec │   │  get_product()   │                │
│     │  (per tenant) │   │  get_order()     │                │
│     └───────────────┘   └─────────────────┘                │
│                                                              │
│   PostgreSQL (tenants + documents)   Google Gemini 2.5 Flash │
└──────────────────────────────────────────────────────────────┘
```

## Stack

| Layer | Technology |
|---|---|
| LLM + Embeddings | Google Gemini 2.5 Flash + gemini-embedding-001 |
| Agent | LangGraph ReAct (`langgraph.prebuilt.create_react_agent`) |
| Vector Store | FAISS (Phase 1) → pgvector / Pinecone / Qdrant (Phase 2) |
| API | FastAPI + SlowAPI rate limiting |
| Database | PostgreSQL (SQLAlchemy async + asyncpg) |
| Sessions | Redis |
| Frontend | Next.js 14 App Router + Tailwind CSS |
| Widget | Vanilla JS (zero dependencies) |
| Auth | JWT (dashboard) + API key (widget) |
| Infra | Docker + nginx + GitHub Actions |

---

## Quick Start (Local)

### Prerequisites
- Python 3.12+
- Node 18+
- PostgreSQL 14+ running locally
- Redis running locally
- [Google AI Studio API key](https://aistudio.google.com/apikey)

### 1. Clone & configure

```bash
git clone <repo-url>
cd rag_agent
cp .env.example .env
# Edit .env — set GEMINI_API_KEY, DATABASE_URL, REDIS_URL
```

### 2. Create database

```bash
createdb ragagent
```

### 3. Run backend

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### 4. Run frontend

```bash
cd frontend
npm install
npm run dev
# Opens at http://localhost:3000
```

### 5. Verify

```bash
curl http://localhost:8000/v1/health
# {"status":"ok","index_ready":true,"doc_count":0,...}
```

---

## Docker (Local — requires Docker Hub access)

```bash
cp .env.example .env  # fill in GEMINI_API_KEY
docker compose up --build
```

Backend: `http://localhost:8000` | Swagger: `http://localhost:8000/docs`

---

## API Overview

Base URL: `http://localhost:8000/v1`

Auth: `Authorization: Bearer <jwt>` (dashboard) or `X-API-Key: <key>` (widget)

| Endpoint | Method | Description |
|---|---|---|
| `/v1/auth/register` | POST | Register tenant → get API key + JWT |
| `/v1/auth/login` | POST | Login → get API key + JWT |
| `/v1/tenant` | GET | Get authenticated tenant info |
| `/v1/chat` | POST | Chat with the agent |
| `/v1/session/{id}` | DELETE | Clear session history |
| `/v1/ingest` | POST | Upload document (.pdf .txt .docx .md) |
| `/v1/documents` | GET | List documents |
| `/v1/documents/{name}` | PUT | Replace document |
| `/v1/documents/{name}` | DELETE | Delete document |
| `/v1/health` | GET | Health check |
| `/admin/tenants` | GET | List all tenants (admin key) |

Full interactive docs: `http://localhost:8000/docs`

---

## Embeddable Widget

Add to any webpage:

```html
<script
  src="https://your-domain.com/static/widget.js"
  data-api-key="sk-your-client-api-key"
  data-title="Acme Support"
  data-theme="light"
  data-position="bottom-right">
</script>
```

| Attribute | Required | Default | Options |
|---|---|---|---|
| `data-api-key` | Yes | — | — |
| `data-api-url` | No | `/v1/chat` | any URL |
| `data-title` | No | `"Assistant"` | any string |
| `data-placeholder` | No | `"Ask me anything..."` | any string |
| `data-theme` | No | `"light"` | `"light"` / `"dark"` |
| `data-position` | No | `"bottom-right"` | `"bottom-right"` / `"bottom-left"` |

---

## Running Tests

```bash
cd backend
pip install aiosqlite  # one-time
pytest tests/ -v
```

Tests use in-memory SQLite + mocked LLM/embeddings — no Gemini API key needed.

---

## Production Deployment (Railway + Vercel)

Primary path: **backend on [Railway](https://railway.app), frontend on [Vercel](https://vercel.com)**,
with managed **[Neon](https://neon.tech)** Postgres and **[Upstash](https://upstash.com)** Redis. All
four have free tiers and provide automatic HTTPS. Both services auto-deploy on push to `main`.

### 1. Provision managed services
- **Neon** → create a project, copy the connection string, and use the `+asyncpg` form:
  `postgresql+asyncpg://USER:PASS@ep-xxx.REGION.aws.neon.tech/dbname`
- **Upstash** → create a Redis database, copy the **TLS** URL: `rediss://default:PASS@HOST:PORT`

### 2. Backend on Railway
- New project → **Deploy from GitHub repo**, set **root directory = `backend/`**
  (build config is committed in `backend/railway.json` — Dockerfile builder, healthcheck `/v1/health`, 1 replica).
- Add a **Volume** mounted at `/data` (FAISS indexes + uploaded docs must survive redeploys —
  Railway's container filesystem is ephemeral).
- Set environment variables:

  | Var | Value |
  |---|---|
  | `DATABASE_URL` | Neon `postgresql+asyncpg://…` |
  | `REDIS_URL` | Upstash `rediss://…` |
  | `GEMINI_API_KEY` | your Gemini key |
  | `JWT_SECRET_KEY` | long random string |
  | `ADMIN_KEY` | strong admin key |
  | `EMBEDDING_BACKEND` | `gemini` (avoids loading torch in the container) |
  | `EMBEDDING_MODEL` | `models/gemini-embedding-001` |
  | `VECTOR_BACKEND` | `faiss` |
  | `FAISS_INDEX_PATH` | `/data/faiss_index` |
  | `INPUT_DOCS_PATH` | `/data/input_docs` |
  | `ALLOWED_ORIGINS` | `https://<your-app>.vercel.app` |

  > FAISS + a single volume means the backend runs **one replica**. Switch to Phase 2 (pgvector)
  > to scale horizontally.

### 3. Frontend on Vercel
- Import the repo → **root directory = `frontend/`** (Next.js auto-detected).
- Set `NEXT_PUBLIC_API_URL=https://<your-app>.up.railway.app`.
- After it deploys, put the Vercel URL into Railway's `ALLOWED_ORIGINS` and redeploy the backend.

### 4. Verify
```bash
curl https://<your-app>.up.railway.app/v1/health   # → {"status":"ok",...}
```
Then register → upload a doc → chat on the Vercel URL. Trigger a Railway redeploy and confirm the
tenant + documents survive (proves the volume + Neon persistence).

---

## Production Deployment (GCP VM — alternative)

A self-hosted Option B (single VM running `docker-compose.prod.yml` with nginx + postgres + redis)
is also scaffolded. The `deploy-gcp.yml` workflow is **manual-only** (`workflow_dispatch`).

1. Set GitHub Secrets: `GCP_VM_HOST`, `GCP_VM_USER`, `GCP_SSH_KEY`
2. Create `.env.prod` on the VM with production values

```bash
# On the GCP VM (first-time setup)
git clone <repo-url> ~/rag_agent
cd ~/rag_agent
cp .env.example .env.prod  # fill in production values
docker compose -f docker-compose.prod.yml up -d
```

SSL via Let's Encrypt:
```bash
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d api.yourdomain.com
```

---

## Multi-Tenancy

- Each tenant gets a unique `tenant_id` and `api_key` at registration
- All data (documents, vectors, sessions) is fully isolated per tenant
- Redis keys: `session:{tenant_id}:{session_id}`
- FAISS indexes: `faiss_index/{tenant_id}/`
- Documents: `input_docs/{tenant_id}/`
- Isolation enforced in application code — every query includes `tenant_id`

---

## Phase 2 — Managed Vector Store

Switch from per-rebuild FAISS to per-document ops:

```bash
# In .env
VECTOR_BACKEND=pgvector   # or pinecone / qdrant
```

See `SPEC.md §15` for migration steps.

---

## Implementation Status

| Step | Status |
|---|---|
| 1–12 Backend foundation | ✅ Complete |
| 13 JS Widget | ✅ Complete |
| 14 Tests (40 tests) | ✅ Complete |
| 15–19 Next.js Frontend | ✅ Complete |
| 20 nginx + docker-compose.prod | ✅ Complete |
| 21 GitHub Actions CI/CD | ✅ Complete |
| 22 README | ✅ This file |
| 23 Phase 2 pgvector | Pending |
