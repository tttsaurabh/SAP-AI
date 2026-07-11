# SAP Knowledge AI Assistant

## Overview

A RAG (Retrieval-Augmented Generation) chat assistant over SAP documentation
(ABAP, MDG, S/4HANA, workflows, master data, functional/design specs). Users
upload documents, the backend chunks/embeds/indexes them, and a chat UI
answers questions grounded in the retrieved chunks with citations.

The app also ships an **"SAP Agentic Workbench"** (SNOTE search, ABAP
validation, transition guide, diagnostics). This is currently a
**simulated/demo feature only** — see "Known simulated/demo features" below.
Do not describe it as connected to a real SAP system.

## Stack

- **Frontend**: Next.js 15 (App Router), React 19, TypeScript, Tailwind CSS.
  Lives in `frontend/`.
- **Backend**: FastAPI + SQLAlchemy 2.0 + Postgres. Lives in `backend/app/`.
- **Vector store**: dual backend, selected via `VECTOR_DB_BACKEND` env var —
  `qdrant` or `pinecone` (see `backend/app/services/vector_db.py` and
  `pinecone_db.py`).
- **LLM provider cascade**: Gemini → OpenAI → Anthropic → mock fallback (see
  `backend/app/services/rag_engine.py`). First provider with a configured API
  key wins; if none are configured, a canned mock response is generated.
- **Other infra**: Redis (session cache / task queue), BM25 keyword scoring
  (`rank-bm25` dependency present but current "hybrid search" is SQL `ILIKE`
  — see limitations below).

## Key directories

- `backend/app/api/` — FastAPI routers (auth, documents, chat, admin,
  sap_agentic)
- `backend/app/services/` — ingestion (parser, chunker, embeddings), RAG
  engine, vector DB adapters, SAP Agentic Workbench simulation
- `backend/app/models/models.py` — SQLAlchemy ORM models (source of truth for
  schema, now version-controlled via Alembic — see below)
- `backend/app/schemas/` — Pydantic request/response schemas
- `backend/app/core/` — config (`config.py`, pydantic-settings), DB engine/
  session (`database.py`), auth/security helpers (`security.py`)
- `backend/alembic/` — migrations (see below)
- `frontend/app/` — Next.js routes/pages (`chat`, `admin`, `auth`,
  `workbench`)
- `frontend/lib/api.ts` — typed API client used by the frontend

## How to run

1. Start infra: `docker-compose up -d` (services: `postgres`, `qdrant`,
   `redis` — check `docker-compose.yml` for exact ports/credentials).
2. Backend: `cd backend`, `pip install -r requirements.txt`, configure
   `.env` (see `.env.example`), then `uvicorn app.main:app --reload`.
   - Schema is managed by **Alembic**, not `Base.metadata.create_all`.
     `app/main.py` runs `alembic upgrade head` automatically on startup
     (pointed at `backend/alembic.ini`), so migrations apply on boot just
     like the old auto-create behavior did. To make schema changes: edit
     `app/models/models.py`, then run
     `cd backend && alembic revision --autogenerate -m "..."` and review the
     generated migration before committing it.
3. Frontend: `cd frontend`, `npm install`, `npm run dev` → http://localhost:3000

## Known simulated/demo features

- **SAP Agentic Workbench** (`backend/app/services/sap_agentic_service.py`,
  `frontend/app/workbench/`): SNOTE search, ABAP validation, transition
  guide, and diagnostics all run against a hardcoded `SIMULATED_NOTES` dict
  and canned logic. There is **no real SAP system connection** (no RFC, no
  live SNOTE/OSS lookup). Do not present this as live integration.

## Known limitations

(These are tracked for later implementation phases — do not "fix" them as a
side effect of unrelated work.)

- Document ingestion is synchronous and blocks the request thread; large
  PDFs can take minutes to process.
- Chat "streaming" in the frontend is simulated word-by-word chunking of an
  already-complete response, not true token-level LLM streaming.
- The citation side-drawer UI shows placeholder/summary text rather than the
  actual cited passage from the source chunk.
- "Hybrid search" (`RAGEngine.hybrid_search`) is currently just a SQL
  `ILIKE` keyword scan combined with vector search — there is no real
  full-text/BM25 index, despite `rank-bm25` being a dependency.
- No reranking is actually performed despite `RERANK_ENABLED` /
  `RERANK_MODEL` config flags existing in `core/config.py`.

## Deferred security work

A **separate, security-focused remediation pass** is planned and intentionally
out of scope for this phase. Do not fix these here unless explicitly asked:
privilege escalation in registration, hardcoded default JWT secret,
hardcoded seeded admin credentials, open CORS (`allow_origins=["*"]`), path
traversal on upload, prompt-injection defenses, rate limiting, password
policy.

## Work Log

<!-- One dated subsection per work session. Format: ### YYYY-MM-DD — Phase N: <name>, then bullets of files touched + what changed + follow-ups deferred. -->

### 2026-07-12 — Phase 0: Alembic migrations + CLAUDE.md

- Added `alembic==1.13.2` to `backend/requirements.txt`.
- Scaffolded Alembic under `backend/alembic/` (`backend/alembic.ini`,
  `backend/alembic/env.py`, `backend/alembic/script.py.mako`,
  `backend/alembic/versions/`).
- Configured `backend/alembic/env.py` to import `Base` from
  `app.core.database` and all models from `app.models.models` (so
  `target_metadata = Base.metadata` covers all 6 tables), and to read the
  connection string from `app.core.config.settings.DATABASE_URL` instead of
  duplicating it in `alembic.ini`.
- Created baseline migration
  `backend/alembic/versions/4adb3cd37ee1_baseline_schema.py` reproducing the
  current schema exactly (users, documents, chunks, conversations, messages,
  feedbacks) — reviewed by hand against `models.py`, and smoke-tested
  (`alembic upgrade head` / `alembic downgrade base`) against a throwaway
  sqlite DB.
- Updated `backend/app/main.py` to run `alembic upgrade head` (via
  `alembic.config.Config` + `alembic.command.upgrade`) on startup instead of
  `Base.metadata.create_all(bind=engine)`.
- Created this `CLAUDE.md`.
- Follow-ups deferred: everything under "Known limitations" and "Deferred
  security work" above; no live database was available to run the migration
  against in this environment, so `alembic upgrade head` has only been
  verified against sqlite, not Postgres.
