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
- **Other infra**: Redis (session cache / task queue). Hybrid search's
  keyword leg uses real Postgres full-text search (`tsvector`/GIN index,
  see Phase 4) — the `rank-bm25` dependency that used to sit unused
  alongside a SQL `ILIKE` scan has been removed.

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

- ~~Document ingestion is synchronous and blocks the request thread~~ —
  **fixed in Phase 3**: ingestion now runs via FastAPI `BackgroundTasks`
  after the upload request returns. See the Phase 3 Work Log entry.
- ~~Chat "streaming" in the frontend is simulated word-by-word chunking of
  an already-complete response~~ — **fixed in Phase 3**: the SSE endpoint
  now forwards real per-token deltas from the provider SDKs' native
  streaming interfaces. See the Phase 3 Work Log entry.
- ~~"Hybrid search" (`RAGEngine.hybrid_search`) is currently just a SQL
  `ILIKE` keyword scan combined with vector search — there is no real
  full-text/BM25 index, despite `rank-bm25` being a dependency.~~ — **fixed
  in Phase 4**: the keyword-search leg now uses real Postgres full-text
  search (`plainto_tsquery`/`ts_rank` over a generated `tsvector` column +
  GIN index). **Postgres-only** — see the Phase 4 Work Log entry for the
  SQLite limitation this introduces.
- ~~No reranking is actually performed despite `RERANK_ENABLED` /
  `RERANK_MODEL` config flags existing in `core/config.py`.~~ — **fixed in
  Phase 4**: a real cross-encoder reranker (`backend/app/services/reranker.py`)
  now consumes both flags. See the Phase 4 Work Log entry.

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

### 2026-07-12 — Phase 3: Real streaming + async ingestion

Non-security remediation fixing two items flagged by the architecture
review: fake word-by-word "streaming" of an already-complete LLM response,
and synchronous in-request document ingestion blocking the upload request
for 170-210s on large PDFs (per `backend/ingest_log.txt`). Verified against
a scratch SQLite DB (`alembic upgrade head` / `downgrade -1` / re-`upgrade
head` round-trip) plus targeted scripts exercising the new pieces directly
(not via `TestClient`, since `fastapi` still isn't installed in this
sandbox — same limitation as Phases 0-2): an ORM round-trip on the new
`Document.error_message` column through a fresh `SessionLocal()` session
(mirroring what the background task actually does), `RAGEngine
.build_citations` against stubbed chunks/response text, the streaming
fallback-cascade logic (`RAGEngine._stream_llm_response`) with fake
provider generators covering pre-first-token-failure fallback,
mid-stream-failure propagation, and the mock-fallback path, and a
standalone asyncio script validating the sync-generator-to-`asyncio.Queue`
thread-bridge pattern used in `chat.py` (ordered delivery, mid-stream
producer exceptions, and early consumer disconnect). `backend/tests
/test_basic.py` still passes (3/3, `python -m unittest`). `npx tsc --noEmit`
on `frontend/` passes with zero errors.

**1. Real LLM streaming** (`backend/app/services/rag_engine.py`,
`backend/app/api/chat.py`):
- `rag_engine.py`: extracted `_build_prompt` (prompt construction) and
  `build_citations` (the `[N]`-marker regex parse + citation dict
  formatting) out of `generate_response` into standalone static methods so
  both the non-streaming and streaming code paths share the exact same
  logic instead of two copies drifting apart. Added `_mock_fallback_text`
  (same canned local response as before, now reusable).
- Added three provider-specific **streaming** generators, one per SDK,
  each yielding raw text deltas as the SDK produces them — no artificial
  buffering:
  - `_stream_gemini`: `genai.GenerativeModel(...).generate_content(prompt,
    stream=True)`, iterating chunks and yielding `chunk.text` (guarded
    with try/except per-chunk, since `.text` can raise on a chunk with no
    parts, e.g. a safety-filtered piece — one bad chunk no longer kills
    the whole stream).
  - `_stream_openai`: `client.chat.completions.create(..., stream=True)`,
    yielding `chunk.choices[0].delta.content` guarded against `None`/empty
    choices (final chunk, role-only deltas).
  - `_stream_anthropic`: `client.messages.stream(...)` as a context
    manager, yielding from `stream.text_stream`.
- `_stream_llm_response(prompt, chunks)`: reproduces the same provider
  fallback order as `generate_response` (Gemini → OpenAI → Anthropic →
  mock), but adapted for the fact that naive fallback doesn't work once
  real tokens have reached the client over SSE. Each provider generator is
  consumed with a `yielded_any` flag: if it raises (or produces nothing)
  **before** yielding any token, the cascade moves on to the next
  provider exactly as before; if it raises **after** yielding at least one
  token, the exception is re-raised (propagated to the caller) instead of
  silently switching providers — those tokens already reached the client
  and can't be un-sent. Verified both branches with fake provider
  generators (see verification note above).
- `stream_response(db, collection_name, query, conversation_history,
  chunks_out=None)`: the new public streaming entry point. A generator
  that does the hybrid search up front (same as `generate_response`),
  yields the canned "not available" string directly and returns if zero
  chunks matched (no LLM call), otherwise builds the prompt and delegates
  to `_stream_llm_response`. `chunks_out`, if passed a list, is populated
  in place with the retrieved chunks before the first token is yielded, so
  the caller can build citations after the generator is exhausted via
  `RAGEngine.build_citations(full_text, chunks_out)` — citations depend on
  the complete `[N]`-marker text, so they're still computed post-hoc, but
  now from text that was actually streamed rather than generated
  up-front.
- **Documented behavior change**: `generate_response`'s knowledge-boundary
  safety net re-scans the *complete* response text for the phrase
  "information is not available" and, if found anywhere, discards the
  whole response in favor of the canned boundary string. That retroactive
  whole-response replacement is **not reproduced in the streaming path** —
  by the time the full text is available, its tokens have already been
  streamed to the client over SSE and cannot be un-sent. The only boundary
  case still honored in `stream_response` is the upfront one (zero
  retrieved chunks → emit the canned string directly without calling any
  LLM), which is the common case this existed for. This is an intentional,
  necessary consequence of real streaming, not an oversight.
- `chat.py`'s `/conversations/{conv_id}/stream` endpoint: replaced the
  "generate full response in an executor, then re-chunk word-by-word with
  `asyncio.sleep(0.01)`" logic with a real bridge from the synchronous
  provider-SDK streaming generator to the async SSE response. Concretely:
  a plain `threading.Thread` runs `RAGEngine.stream_response(...)` and
  pushes each yielded delta into an `asyncio.Queue` via
  `loop.call_soon_threadsafe(queue.put_nowait, ...)`; the async
  `event_generator()` coroutine `await`s the queue and forwards each delta
  as an SSE `content` event as it arrives — cadence is now real
  token-arrival timing, not an artificial `sleep`. After the producer
  signals completion (a sentinel object) or the loop breaks, the full
  accumulated text is used to build citations
  (`RAGEngine.build_citations`) and the `Message`/`Citation` DB writes
  happen exactly as before (same shapes, same SSE `citations` + `done`
  events) — the SSE wire protocol is unchanged, so `frontend/lib/api.ts`'s
  `streamResponse` needed no changes; only the `content` event cadence
  changed from artificial-typewriter to real per-token.
- **Disconnect handling** (actual behavior achieved, not aspirational):
  the endpoint now takes `request: Request` and calls `await request
  .is_disconnected()` every 5 forwarded tokens (not every single one, since
  it's itself an async call). If the client has disconnected, the consumer
  coroutine stops pulling from the queue and returns immediately *without*
  saving the assistant `Message`/`Citation` rows for that turn — an
  abandoned stream leaves no orphaned "assistant said nothing" message.
  What is **not** achieved: true cancellation of the in-flight provider
  SDK call. The background `threading.Thread` is not signaled to stop; it
  keeps running the synchronous Gemini/OpenAI/Anthropic streaming call to
  completion (or failure) in the background and its output is simply
  discarded (nothing is left draining the queue). This is the documented
  best-effort behavior the task explicitly allows for ("full cancellation
  ... is not always possible") — the thread is a daemon thread so it does
  not block process shutdown, and it terminates on its own once the
  underlying HTTP call to the LLM provider finishes.
- The DB session (`db`, from `Depends(get_db)`) is used from the
  background thread (inside `stream_response`/hybrid_search) and, after
  the thread signals done, from the async coroutine (citation build +
  message insert) — sequentially, never concurrently from two threads at
  once (the coroutine only touches `db` again after the queue delivers the
  terminal sentinel), which is the same safety property the prior
  `run_in_executor`-based code already relied on.

**2. Async document ingestion** (`backend/app/api/documents.py`,
`backend/app/models/models.py`, `backend/app/schemas/schemas.py`,
`backend/alembic/versions/6d3f9a1c8b52_phase3_document_error_message.py`):
- **Decision: FastAPI `BackgroundTasks`, not Celery/RQ, and Redis stays
  unused — deliberately, not an oversight.** `docker-compose.yml`
  provisions a `redis` service, but nothing in the app reads from it. For
  this single-instance FastAPI deployment, `BackgroundTasks` gives
  in-process, no-new-infra async execution that's good enough: the
  background function runs in the same process after the HTTP response is
  sent, no message broker, no separate worker process, no serialization of
  job arguments across a queue. The tradeoffs accepted knowingly: a
  background task is lost if the process crashes/restarts mid-ingestion
  (no persistence/retry across restarts, unlike a Celery/RQ queue backed
  by Redis), and there's no fan-out to multiple worker processes/machines
  for very high ingestion volume. Given the app's current single-instance
  deployment and the fact that the *problem being fixed* was "the request
  blocks," not "we need horizontal ingestion throughput," `BackgroundTasks`
  is the appropriately-sized fix. Wiring up Celery/RQ on top of the
  already-provisioned Redis container is a reasonable future step if
  ingestion volume or reliability requirements grow — tracked as a
  follow-up, not attempted here.
- `documents.py`'s `POST /upload` handler is now split: the fast path
  validates the file, saves it to disk, does the `Collection` get-or-create
  + embedding-model-compatibility check (unchanged from Phase 1), creates
  the `Document` row with `status=DocumentStatus.PROCESSING`, commits, and
  returns the `201` response immediately (same response shape as before —
  `DocumentResponse`). It then calls `background_tasks.add_task
  (process_document_ingestion, document_id=..., file_path=..., filename=
  ..., collection_name=...)`.
- New module-level function `process_document_ingestion(document_id,
  file_path, filename, collection_name)` (not a route handler) contains
  the actual parse → chunk → insert-chunks → vector-upsert → status-update
  pipeline that used to run inline in the request handler. **Critically**,
  it does **not** reuse the request-scoped `Session` from `Depends
  (get_db)` — that session is closed by the time a `BackgroundTasks`
  callback runs (FastAPI runs background tasks after the response has been
  sent, by which point the request's `finally: db.close()` in `get_db()`
  has already executed). It opens its own session via `SessionLocal()`
  (`backend/app/core/database.py`'s existing factory) and closes it in a
  `finally` block — verified via a scratch-SQLite script that opens a
  second `SessionLocal()` session mid-"task" and confirms writes made in
  the first session are visible, matching how a real background task
  would see the already-committed `Document` row from the fast path.
- On any exception during ingestion, `process_document_ingestion` sets
  `Document.status = DocumentStatus.FAILED` and now also sets the new
  `Document.error_message` column (truncated to 2000 chars) with the
  exception text, instead of leaving a `FAILED` document with zero
  explanation. Wrapped in its own inner try/except so a failure to *record*
  the failure (e.g. the DB connection itself is down) doesn't raise an
  unhandled exception out of a background task (which FastAPI would just
  log and swallow silently) — it's logged via `loguru` instead.
- **New column**: `Document.error_message` (`Text`, nullable) added to
  `backend/app/models/models.py`, with Alembic migration
  `6d3f9a1c8b52_phase3_document_error_message.py` (purely additive
  `ADD COLUMN`, no data migration needed since every existing row simply
  gets `NULL`). Verified `upgrade head` / `downgrade -1` / re-`upgrade
  head` round-trip against scratch SQLite. `DocumentResponse` in
  `schemas.py` gained `error_message: Optional[str] = None` so the admin
  document list surfaces it.
- **Known race condition (not fixed here, flagging for awareness)**:
  `process_document_ingestion` checks the `Document` row still exists at
  the start, but if an admin calls `DELETE /api/documents/{id}` *after*
  that check but *while* the background task is still running, the task
  will go on to insert `Chunk` rows against a `document_id` that no longer
  exists. `Chunk.document_id` has `ondelete="CASCADE"` but that only
  protects against orphaned rows for chunks that already existed at
  delete-time, not chunks inserted by a task that's still in flight. This
  is a pre-existing class of race (synchronous ingestion had the same
  window, just a much smaller one) that got wider now that ingestion can
  run for minutes after the row is visible/deletable in the admin UI —
  not fixed in this phase, tracked as a follow-up.

**3. Frontend polling** (`frontend/app/admin/page.tsx`,
`frontend/lib/api.ts`):
- `DocumentInfo.error_message?: string | null` added to `frontend/lib
  /api.ts` (matches the new backend field).
- `admin/page.tsx`: added a second `useEffect` that starts a
  `setInterval(loadDocuments, 3000)` whenever any listed document has
  `status === "processing"`, and clears it (via the effect's cleanup
  function) otherwise — plain polling, not a websocket/SSE channel, per
  the plan's explicit "keep this minimal" guidance. Effect re-runs on
  every `documents` state change (i.e. every poll tick), which
  recreates the interval each cycle rather than letting one interval run
  indefinitely; functionally equivalent (still polls every ~3s while
  anything is processing, stops the moment nothing is) at the cost of a
  minor, harmless extra timer churn — not worth a `useRef`-based
  micro-optimization for a 3s admin-page poll.
- The `failed` status badge now has a `title` tooltip showing
  `doc.error_message` (falling back to a generic "no error details
  recorded" string for documents that failed before this phase, whose
  `error_message` is `NULL`).

**Follow-ups for later phases**:
- Wire Celery/RQ onto the already-provisioned Redis container if
  ingestion volume/reliability needs outgrow in-process `BackgroundTasks`
  (see the Decision note above).
- The `Document` delete-during-background-ingestion race described above
  is not fixed in this phase.
- Postgres-specific behavior (the `documents.error_message` `ADD COLUMN`,
  and `BackgroundTasks` running under a real Postgres connection pool
  rather than SQLite) is unverified against a live Postgres instance —
  same limitation as every prior phase in this sandbox.
- No live LLM API keys were available in this environment, so the actual
  provider SDK streaming calls (`stream=True` / `messages.stream()`)
  were verified via fake provider generators exercising the fallback/
  propagation logic, not against real Gemini/OpenAI/Anthropic endpoints.
  Re-verify token-by-token behavior against live keys before relying on
  this in production.

### 2026-07-12 — Phase 4: Real hybrid search + reranker

Non-security remediation fixing two items flagged by the architecture
review: `RAGEngine.hybrid_search`'s "keyword search" leg was a
`Chunk.text.ilike('%word%')` full-table scan with no index (despite
`rank-bm25` sitting in `requirements.txt`, never actually imported/used
anywhere), and `RERANK_ENABLED`/`RERANK_MODEL` were dead config flags in
`core/config.py`/`.env.example` with zero references anywhere else in the
codebase (confirmed by grep before starting). `fastapi` and
`sentence-transformers` are still not installed in this sandbox (same
limitation as every prior phase), and no live Postgres instance was
available either, so verification here is code-review-level plus targeted
logic tests against mocks/fakes, not a live end-to-end run — see the
per-item verification notes below.

**1. Real Postgres full-text search** (`backend/app/models/models.py`,
`backend/app/services/rag_engine.py`,
`backend/alembic/versions/e2a7c4f91b30_phase4_fulltext_search.py`):
- New hand-written migration adds a **Postgres-only** generated column:
  `ALTER TABLE chunks ADD COLUMN text_search tsvector GENERATED ALWAYS AS
  (to_tsvector('english', text)) STORED` plus `CREATE INDEX
  idx_chunks_text_search ON chunks USING GIN(text_search)`. Alembic can't
  autogenerate `GENERATED ALWAYS AS` columns, so this is raw `op.execute`
  SQL, per the plan. Both `upgrade()`/`downgrade()` check
  `op.get_bind().dialect.name` and no-op on any non-Postgres dialect
  instead of raising.
- `Chunk.text_search` mapped in `models.py` as
  `deferred(Column(TSVECTOR, Computed("to_tsvector('english', text)",
  persisted=True)))`: `Computed(...)` marks it server-generated so
  SQLAlchemy never includes it in INSERT/UPDATE value lists (confirmed via
  a scratch script: the ORM issues `INSERT INTO chunks (...) VALUES (...)
  RETURNING id, text_search` — no `text_search` in the value list, only in
  the RETURNING clause); `deferred()` keeps it out of the default SELECT
  column list for ordinary `db.query(Chunk)`/`select(Chunk)` reads
  elsewhere in the codebase — confirmed by compiling a `select(Chunk)...`
  statement against the Postgres dialect and inspecting the column list
  (see verification note below).
- **Known, deliberate SQLite limitation** (documented at length in the
  `Chunk.text_search` comment in `models.py`): because the migration only
  adds this physical column on Postgres, a SQLite-backed `chunks` table
  genuinely lacks it. SQLAlchemy still references the mapped column when
  building the generated INSERT's `RETURNING` clause regardless of
  `deferred()` (deferred only affects SELECT-time loading, not
  INSERT/UPDATE statement generation) — confirmed empirically: inserting a
  `Chunk` row against a scratch SQLite DB that had this migration applied
  (a no-op there) fails with `sqlite3.OperationalError: no such column:
  text_search`. This means, unlike Phases 0-3, **this migration/column
  could not be round-trip-verified against SQLite for real DB
  operations** — only the migration chain itself was round-tripped
  (`upgrade head` / `downgrade -1` / re-`upgrade head` against a scratch
  SQLite DB, which succeeds because both directions correctly no-op on a
  non-Postgres dialect). `backend/tests/test_basic.py` is unaffected
  because none of its 3 tests touch a real DB (`RAGEngine.hybrid_search`
  and the DB session are both mocked in the one test that goes through
  `RAGEngine`). No live Postgres instance was available in this sandbox to
  verify the actual generated-column/GIN-index DDL or a real insert/query
  round-trip — the SQL was reviewed by hand and the ORM-side query was
  compiled (not executed) against the Postgres dialect to check syntax
  (see below). Re-verify against a real Postgres instance before deploying.
- `RAGEngine._db_keyword_search` (`rag_engine.py`): replaced the
  keyword-extraction-plus-`ILIKE`-`OR`-chain loop with
  `func.plainto_tsquery('english', query)` filtered via
  `Chunk.text_search.op('@@')(tsquery)` and ordered by
  `func.ts_rank(Chunk.text_search, tsquery).desc()`. Collection scoping is
  unchanged (`Document.collection_name == collection_name` — verified live
  that `hybrid_search`/`_db_keyword_search` still key off
  `collection_name`, not `collection_id`; the Phase 1 decision to keep
  `collection_name` as the source of truth for search/vector-store paths
  is still in effect, so this fix didn't touch that). Verified the exact
  generated SQL by compiling the equivalent `select(Chunk).join(Document)
  .where(...)` statement against `sqlalchemy.dialects.postgresql.dialect()`
  (not executed against a real DB): produces
  `... WHERE documents.collection_name = %(...)s AND (chunks.text_search @@
  plainto_tsquery(%(...)s, %(...)s)) ORDER BY ts_rank(chunks.text_search,
  plainto_tsquery(%(...)s, %(...)s)) DESC LIMIT %(...)s`, and confirmed
  `text_search` does NOT appear in the SELECT column list (the `deferred()`
  wrapper working as intended).
- Removed `rank-bm25==0.2.2` from `backend/requirements.txt` — grep
  confirmed zero references to it anywhere in the codebase before removal
  (it was never imported), and real Postgres FTS now replaces the role the
  `ILIKE` scan used to occupy.

**2. Real cross-encoder reranker** (new
`backend/app/services/reranker.py`, `backend/app/services/rag_engine.py`):
- New `Reranker` class lazily loads and caches a
  `sentence_transformers.CrossEncoder` as a class-level singleton, mirroring
  `EmbeddingsService._local_model`'s exact caching pattern in
  `embeddings.py` (lazy load on first use, guarded by a class attribute,
  cached thereafter). Default model is `settings.RERANK_MODEL` if set, else
  `cross-encoder/ms-marco-MiniLM-L-6-v2`. Logs a one-time `logger.warning`
  (upgraded from `embeddings.py`'s `logger.info` on local-model load, since
  scoring N pairs per request is a heavier, more latency-visible operation)
  on first model load, warning about latency.
- `Reranker.rerank(query, candidates)` scores `(query, candidate["text"])`
  pairs via `model.predict(pairs)`, adds a `rerank_score` key to each
  candidate dict (preserving all existing keys), and returns candidates
  sorted descending by score. No-ops (returns input unchanged) when
  `RERANK_ENABLED` is false, fewer than 2 candidates are passed,
  `sentence_transformers` isn't installed, or scoring raises for any reason
  — reranking is an enhancement, never a hard dependency for retrieval to
  keep working.
- `RAGEngine.hybrid_search`: when `settings.RERANK_ENABLED` is true, the RRF
  fusion/dedup loop now collects up to `max(limit * 3, 15)` candidates
  (instead of stopping at `limit`) before calling `Reranker.rerank(query,
  final_results)`, then truncates to `limit` afterward. When the flag is
  false, `fusion_limit == limit`, so the RRF loop stops exactly where it
  always did and `Reranker.rerank` (called unconditionally, but itself a
  no-op when the flag is off) returns the list unchanged — **verified this
  is a byte-for-byte no-op when disabled**, not just "close enough": with
  `RERANK_ENABLED=False` and 20 fake semantic hits fed through a mocked
  vector backend, `hybrid_search` returned exactly 5 results and the
  (mocked) `Reranker.rerank` was invoked with exactly 5 candidates, no
  widening. With `RERANK_ENABLED=True` under the same fake data,
  `Reranker.rerank` was invoked with exactly 15 candidates and the final
  result was still truncated to 5.
- Reranking is applied to the original (non-SAP-abbreviation-expanded)
  `query` string, not `expand_query`'s output — a cross-encoder scores
  actual query/passage semantic relevance and is expected to perform better
  against the user's real phrasing than a query mechanically padded with
  expansion terms (e.g. `"BP" -> "BP Business Partner"`); the expanded
  query is still what both the vector search and full-text search legs use
  for recall.
- **Verification**: `sentence_transformers` is not installed in this
  sandbox (confirmed via `python -c "import sentence_transformers"` ->
  `ModuleNotFoundError`), so the real `CrossEncoder`/model-download path is
  **not verified end-to-end here**. What *is* verified: `Reranker.rerank`'s
  full branching logic (flag-off no-op, missing-package no-op, <2-candidate
  no-op, exception-during-predict fallback, score-descending sort, and
  model-instance caching/reuse across calls) against a hand-written fake
  `CrossEncoder` class monkeypatched into the module in place of the real
  one, plus the `hybrid_search` fusion-widening integration behavior
  described above with `Reranker.rerank` itself mocked out. Re-verify
  against the real `sentence-transformers` package/model download before
  relying on this in production.

**Commits**: (a) full-text search (`models.py`, migration,
`rag_engine.py`'s `_db_keyword_search`, `requirements.txt`); (b) reranker
(`reranker.py`, `rag_engine.py`'s `hybrid_search` fusion/rerank wiring).

**Follow-ups for later phases**:
- Postgres-specific DDL in the new migration (generated column, GIN index)
  is unverified against a live Postgres instance — same class of limitation
  as prior phases' Postgres-only paths, but notably this phase's SQLite
  fallback verification path is narrower than prior phases' (chain-only,
  not data-operation-level — see above).
- If `Document.collection_name` is ever dropped in favor of `collection_id`
  (tracked since Phase 1), `_db_keyword_search`'s collection filter needs
  to move with it — not done here, out of scope for this pass.
- No live LLM/reranker model download was exercised; the cross-encoder path
  is verified by code review + mocked-class logic tests only, as noted
  above.
