# Implementation Progress

Track status of all 23 steps from SPEC.md §13.

## Phase 1 — Backend Foundation

- [x] **Step 1** — Repo scaffold: `.env.example`, `.gitignore`, `docker-compose.yml`
- [x] **Step 2** — `backend/app/config.py` — Pydantic Settings
- [x] **Step 3** — `backend/app/database.py` — SQLAlchemy async + PostgreSQL
- [x] **Step 4** — `backend/app/models.py` — Pydantic schemas
- [x] **Step 5** — `backend/app/logger.py` — JSON structured logging
- [x] **Step 6** — `backend/app/auth.py` — JWT + API key dependencies
- [x] **Step 7** — `backend/app/vector_store.py` — VectorStore Protocol + FAISSVectorStore
- [x] **Step 8** — `backend/app/session.py` — Redis-backed sessions
- [x] **Step 9** — `backend/app/ingest.py` — Document pipeline (Phase 1 FAISS)
- [x] **Step 10** — `backend/app/tools.py` — Agent tools
- [x] **Step 11** — `backend/app/agent.py` — ReAct AgentExecutor
- [x] **Step 12** — `backend/app/main.py` — All routes + middleware

## Phase 1 — Widget + Tests

- [x] **Step 13** — `static/widget.js` — Vanilla JS embeddable widget
- [x] **Step 14** — `backend/tests/` — pytest suite (conftest + 4 test files, 40 tests pass)

## Phase 1 — Frontend

- [x] **Step 15** — `frontend/` scaffold — Next.js 14 App Router, TypeScript, Tailwind
- [x] **Step 16** — `frontend/lib/api.ts` — Typed API client
- [x] **Step 17** — Register + Login pages
- [x] **Step 18** — Dashboard — Chat tab (`ChatPanel.tsx`)
- [x] **Step 19** — Dashboard — Documents tab (`DocumentsPanel.tsx`, `UploadZone.tsx`)

## Phase 1 — Infra + Docs

- [x] **Step 20** — `nginx/nginx.conf` + `docker-compose.prod.yml`
- [x] **Step 21** — `.github/workflows/ci.yml` + `deploy-gcp.yml`
- [x] **Step 22** — `README.md` — architecture diagram + setup guide

## Phase 2 — Managed Vector Store

- [ ] **Step 23** — `PGVectorStore` in `vector_store.py` + `chunks` table migration script
