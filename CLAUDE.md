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

### 2026-07-12 — Phase 1: Schema hardening

Non-security schema-hardening pass following the architecture review. All
changes verified against a scratch SQLite DB (`alembic upgrade head` /
`downgrade base`, plus an ORM round-trip script exercising the new enum
columns and Collection/Chunk fields) — no live Postgres was available in
this environment, so Postgres-specific paths (native `CREATE TYPE`/`ALTER
... USING`) are written carefully but not live-tested. `fastapi` itself
isn't installed in this sandbox, so `app.main` / the HTTP layer couldn't be
booted end-to-end; verification instead went through `SessionLocal` +
the ORM models directly, and `backend/tests/test_basic.py` (3/3 pass via
`python -m unittest`, `pytest` not installed here).

**1. Missing FK indexes** (`backend/app/models/models.py`): added
`index=True` to `Chunk.document_id`, `Conversation.user_id`,
`Message.conversation_id`, `Feedback.message_id`.

**2. Collections as a first-class table**:
- New `Collection` model (`id`, `name` unique+indexed, `created_by` FK to
  `users.id`, `created_at`, plus `embedding_model`/`embedding_version` — see
  item 3) in `backend/app/models/models.py`.
- `Document.collection_id` (FK to `collections.id`, nullable) added
  alongside the existing `Document.collection_name`. **Decision**:
  `collection_name` is kept as a denormalized display-cache column for this
  phase rather than dropped, to avoid a bigger breaking change to the
  upload/list/search API surface (it's still what `vector_db.py` /
  `pinecone_db.py` use as the namespace/collection key, and what the
  frontend collection picker reads). `collection_id`/`Collection` is the
  source of truth for embedding-model bookkeeping. Documented in a comment
  on `Document.collection_name` in `models.py`. Follow-up for a later phase:
  fully migrate collection lookups to `collection_id` and drop
  `collection_name`, and switch the vector store namespace key to
  `collection_id` instead of the (renameable) name string.
- `backend/app/api/documents.py`'s upload flow now does get-or-create by
  name (`_get_or_create_collection`) and sets `Document.collection_id`.
- `backend/app/api/admin.py`: existing `GET /api/admin/collections` is
  unchanged in shape (`List[str]`, backward compatible with
  `frontend/lib/api.ts`'s `listCollections()` and its callers in
  `admin/page.tsx` / `chat/page.tsx`) — kept deliberately minimal per the
  task's fallback option, since a full frontend refactor to `{id, name}`
  objects was out of scope for this pass. Added a new, additive
  `GET /api/admin/collections/full` endpoint returning real `Collection`
  rows (`CollectionResponse` schema in `schemas.py`) for future frontend
  wiring. **Follow-up**: wire the frontend collection picker to
  `collections/full` + `collection_id` in a later phase.
- Alembic migration `backend/alembic/versions/9ff13957a9db_phase1_schema_hardening.py`
  creates the `collections` table and `documents.collection_id`, then runs
  raw-SQL backfill (`op.execute`): inserts distinct `collection_name` values
  into `collections`, then sets `documents.collection_id` to match.
  Verified the backfill against seeded data in scratch SQLite.

**3. Embedding/vector-store integrity fixes**:
- Fixed `EmbeddingsService.get_embedding_dimension()` in
  `backend/app/services/embeddings.py`: `text-embedding-3-large` now
  correctly maps to `3072` (was `3074`).
- `Collection.embedding_model` is stamped with `settings.EMBEDDING_MODEL` at
  get-or-create time (first ingest into that collection name). Before every
  upload, `documents.py`'s `_ensure_embedding_model_compatible` compares the
  collection's stored `embedding_model` against the currently configured
  one and raises `HTTPException(409, ...)` on mismatch instead of silently
  mixing embedding spaces in one vector index/namespace.
  `Collection.embedding_version` exists as a column but nothing sets it yet
  (no versioning scheme exists for any single `EMBEDDING_MODEL` value today)
  — left `None`/unused, follow-up for whenever model versioning is
  introduced.
- Added `Chunk.vector_id` (String, nullable). The vector id
  (`f"doc{document_id}_chunk{chunk_index}"`) is now generated exactly once,
  in `backend/app/api/documents.py`'s upload flow, and passed into both
  `Chunk(vector_id=...)` and the chunk dicts handed to
  `vector_backend.upsert_chunks(...)`. `vector_db.py` (Qdrant) and
  `pinecone_db.py` both now read `chunk.get("vector_id")` instead of
  deriving their own formula (each keeps a `... or f"doc{...}_chunk{...}"`
  fallback for any caller that doesn't supply one, e.g. direct test calls).
  Note: Qdrant point ids must be an unsigned int or UUID string (unlike
  Pinecone, which accepts arbitrary strings), so `vector_db.py` derives a
  deterministic `uuid5` from the canonical `vector_id` string for the actual
  Qdrant point id, and stores the canonical string in the point's payload
  under `vector_id` for lookups/debugging — the id is still only *generated*
  in one place, just adapted for Qdrant's id-type constraint at the point of
  use.
- Removed the silent Qdrant `QdrantClient(location=":memory:")` fallback in
  `VectorDBService.get_client()` (`backend/app/services/vector_db.py`) — an
  unreachable/misconfigured Qdrant host now raises
  `RuntimeError("Qdrant unreachable at {host}:{port} — check the Qdrant
  service is running")` instead of silently switching to an in-memory
  instance that loses data on restart.

**4. Enum-ified role/status columns**:
- New `backend/app/core/roles.py`: `Role` (`SUPER_ADMIN = "Super Admin"`,
  `KNOWLEDGE_MANAGER = "SAP Knowledge Manager"`, `CONSULTANT = "SAP
  Consultant"`, `END_USER = "End User"`, `GUEST = "Guest"`),
  `DocumentStatus` (`PROCESSING = "processing"`, `ACTIVE = "active"`,
  `FAILED = "failed"`), `MessageRole` (`USER = "user"`, `ASSISTANT =
  "assistant"`) — all `str, enum.Enum`, values verified by grep against
  existing string literals before creating the file (no new/renamed role or
  status values).
- `User.role`, `Document.status`, `Message.role` in `models.py` now use
  `sqlalchemy.Enum` bound to these Python enums (`values_callable` set so
  the DB stores the `.value` strings, not the Python member names). On
  Postgres this becomes a real native `ENUM` type with a `CHECK`-equivalent
  constraint; on SQLite (no native enum support) it stays a plain
  `VARCHAR` (SQLAlchemy's `Enum` defaults `create_constraint=False`, so no
  `CHECK` is added there — confirmed this matches actual SQLAlchemy 2.0
  behavior, not a bug).
- Alembic migration converts the three columns via
  `sa.Enum(...).create(bind, checkfirst=True)` (dialect-aware: emits
  `CREATE TYPE` on Postgres, no-op on SQLite) + `batch_alter_table(...)`
  with `postgresql_using` for the Postgres cast (batch mode is required so
  the same migration also works on SQLite, which can't `ALTER COLUMN`
  directly). Downgrade drops the columns back to `String` and drops the
  enum types. Enum values are hardcoded inline in the migration file
  (not imported from `app.core.roles`) so the migration stays
  self-contained/immune to future edits of that module, per Alembic
  best practice.
- Updated every string-literal role comparison to use the `Role` enum:
  `backend/app/core/security.py` (`RoleChecker`, `admin_only`,
  `consultant_or_above`, `any_authenticated` — **committed in isolation**,
  see commit list below, purely mechanical literal→enum swap, zero
  authorization-behavior change), `backend/app/api/chat.py` (conversation
  ownership checks + `Message(role=...)` construction, now via
  `MessageRole`), `backend/app/main.py` (seeded default-user roles).
  `backend/app/api/auth.py` was deliberately **not touched** — its
  registration endpoint still assigns `role=user_in.role` (a plain string
  from the client) directly to the enum column; verified via an ORM
  round-trip script that SQLAlchemy's `Enum` type accepts a plain string
  matching a valid value and returns the correct enum member on read-back,
  so this continues to work unchanged. The client-controlled-role-at-
  registration issue itself remains explicitly out of scope (security
  remediation, deferred — see "Deferred security work" above).
  `UserCreate.role` in `schemas.py` stays `Optional[str]` (unchanged) per
  the task's instruction to keep input validation permissive in this phase.

**Commits** (see git log): (a) `backend/app/core/security.py` role-literal
enum swap, isolated; (b) everything else in this phase.

**Follow-ups for later phases**:
- Frontend collection picker still consumes `List[str]` from
  `/api/admin/collections`; wire it to `/api/admin/collections/full` +
  `Collection.id` when a full frontend pass is scheduled.
- Drop `Document.collection_name` once all read paths (vector store
  namespace key, frontend) are migrated to `collection_id`.
- `Collection.embedding_version` is unused (no model-versioning scheme
  exists yet).
- Postgres-specific migration paths (native ENUM creation/cast) are
  unverified against a live Postgres instance — re-verify before deploying
  this migration to a real Postgres environment.
- `fastapi` is not installed in this sandbox; the HTTP/router layer
  (`app.main`, `TestClient`-style tests) could not be exercised end-to-end
  here, only the ORM/model/migration layer.

### 2026-07-12 — Phase 2: Real citations

Non-security remediation fixing the "Source Verification" citation drawer,
which previously rendered a **hardcoded fake placeholder string** for every
citation regardless of which one was clicked, because the backend never
sent real chunk text or a `chunk_id` to begin with. Verified against a
scratch SQLite DB (`alembic upgrade head` / `downgrade -1` / full
`downgrade base` → `upgrade head` round-trip), plus an ORM/service-layer
script exercising `RAGEngine.hybrid_search`'s two origins (keyword-search
`Chunk` rows and a stubbed vector-store hit dict) and `generate_response`'s
citation building, `Citation` row insert, and its FK `ondelete` behavior
(`chunk_id` → NULL on chunk delete, rows CASCADE-deleted with the parent
message — SQLite needed `PRAGMA foreign_keys=ON` enabled explicitly for
this test, since `app/core/database.py` doesn't set it and Postgres
enforces natively either way). `fastapi` still isn't installed in this
sandbox (same limitation as Phases 0/1), so `backend/tests/test_basic.py`
was run via `python -m unittest` (3/3 pass) rather than `pytest`/`TestClient`.

**1. New `Citation` join table** (`backend/app/models/models.py`): `id`,
`message_id` FK → `messages.id` `ON DELETE CASCADE`, `chunk_id` FK →
`chunks.id` `ON DELETE SET NULL` (nullable — a cited chunk can be deleted,
e.g. document reprocessed, without losing the historical citation record),
`rank`, `created_at`. **Purely additive**: `Message.citations` (JSON) is
unchanged and remains the fast denormalized read path for the chat UI;
`citations` (the new table) exists for durable joinability (e.g. "which
chunks get cited most"), not as a replacement. Migration:
`backend/alembic/versions/180c1b30601c_phase2_citation_table.py`.

**2. Backend: `chunk_id` + real `text` threaded through the citation
payload** (`backend/app/services/rag_engine.py`):
- `hybrid_search`'s RRF fusion now sets a `chunk_id` key on every chunk
  dict it produces, regardless of origin: for keyword-search-origin chunks
  (already SQLAlchemy `Chunk` ORM objects) it's just `chunk.id`; for
  semantic-search-origin hits (plain dicts from the vector store payload,
  which carries no DB id) it extends the RRF-keying lookup that already
  existed to recover `chunk_index` (`db.query(Chunk).filter(document_id=...,
  text=...)`) to also capture `chunk_obj.id`.
- `generate_response`'s `[N]`-bracket-citation-marker parsing now includes
  `chunk_id` and the chunk's real `text` (truncated to 1500 chars — a
  generous ceiling above the chunker's ~450-token/1200–1800-char default
  target chunk size, so normal chunks pass through whole) in each citation
  dict. Iteration order changed from `set` (arbitrary) to `sorted(...)` so
  citation `rank` (used by the new `Citation` rows) is deterministic.
- `backend/app/schemas/schemas.py`'s `CitationSchema` gained `chunk_id:
  Optional[int] = None` and `text: str = ""` (defaulted, not required — so
  older `Message.citations` JSON blobs saved before this change, which lack
  `text`/`chunk_id`, still deserialize instead of raising a validation
  error).
- `backend/app/api/chat.py`'s stream handler: after committing the
  assistant `Message` (unchanged), bulk-inserts one `Citation` row per
  citation (`message_id`, `chunk_id`, `rank`=index) in the same request,
  via `db.bulk_save_objects` + `db.commit()`.

**3. Frontend: render real citation text**:
- `frontend/lib/api.ts`'s `Citation` interface gained `chunk_id?: number`
  and `text: string` (matches the backend field names exactly).
- `frontend/app/chat/page.tsx`: the citation badge click handler already
  passed the full citation object into `selectedCitation` state (no change
  needed there). Replaced the hardcoded fake "CITED SEGMENT TEXT" paragraph
  in the Source Verification drawer with `{selectedCitation.text}`, guarded
  by an `if (selectedCitation.text)` check — falls back to an honest
  "Source text unavailable for this citation." message (not fake text) when
  `text` is empty, e.g. for messages saved before this change shipped.

**Follow-ups for later phases**:
- `Collection.embedding_version`, `Document.collection_name` follow-ups
  from Phase 1 are still open (see that entry).
- The new `Citation` table has no API surface yet (no endpoint reads it) —
  it exists for future analytics ("most-cited chunks") but nothing queries
  it today.
- Postgres-specific FK `ondelete` behavior (`SET NULL`/`CASCADE`) is
  enforced natively there; only verified against SQLite with
  `PRAGMA foreign_keys=ON` explicitly enabled in this sandbox (see above).
