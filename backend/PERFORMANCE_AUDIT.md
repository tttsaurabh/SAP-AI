# Performance Audit — Chat Response Latency (2026-07-13)

## Why this exists

The user reported very high chat response latency on the local dev server.
This document is the record of the investigation: what was actually
measured (not estimated), what was fixed, what wasn't, and why. See the
CLAUDE.md Work Log for a summary of the code changes.

Methodology: added permanent request-timing instrumentation
(`backend/app/core/timing.py` + a request middleware in `main.py` + named
phases in the chat/retrieval hot path), then drove the real running server
with real HTTP requests (login, create conversation, chat stream) via
`backend/venv`, reading the actual logged `duration_ms` numbers rather than
estimating from code inspection.

## Headline finding: the dominant cost is Gemini, not local infrastructure

| Query | Retrieval (`hybrid_search`) | Gemini time-to-first-token | Total |
|---|---|---|---|
| 1 (cold, before fixes) | 13.9s *(11.7s of this was a one-time embedding-model load)* | 20.5s | 38.1s |
| 2 (warm, before fixes) | 0.6s | 17.0s | 21.7s |
| 3 (warm, before fixes) | 0.35s | 58.3s | 62.5s |
| 4 (warm, after all fixes) | 2.1s | 23.5s | 26.8s |

`rag_engine.py` calls `genai.GenerativeModel('gemini-3.5-flash').generate_content(prompt, stream=True)`
with no `request_options` timeout, and the prompt itself is small (5 short
context chunks, no huge context — checked `_build_prompt`). Across 4
back-to-back test calls with the same shape of prompt, Gemini's own
time-to-first-token ranged **17-58 seconds**, dwarfing every other
component by 10-100x. This is not something local infrastructure changes
can fix. Only `GEMINI_API_KEY` was configured (`OPENAI_API_KEY`/
`ANTHROPIC_API_KEY` were empty in `.env`), so the existing provider fallback
cascade had nowhere to fail over to even if a timeout were added.

**Status: open.** The user asked to wire up OpenAI/Anthropic as real
fallback providers; this requires API keys that weren't available at the
time of this pass. `rag_engine.py`'s `_stream_gemini`/`_call_llm_cascade`
already contain the fallback logic (`if settings.OPENAI_API_KEY and OpenAI:
...`) — once keys are added to `backend/.env`, the cascade will use them
automatically. Adding an explicit `request_options={"timeout": N}` to the
Gemini call so a stuck request fails over quickly instead of hanging up to
a minute is the other half of this fix, also not yet done. **This is the
single highest-leverage remaining fix** — bigger than everything else in
this document combined.

## What "very high latency" actually broke down into (before any fix)

Real numbers from the first (cold) request:

```
chat.conversation_lookup        70ms
chat.save_user_message         282ms
chat.load_history                71ms
hybrid_search.keyword_leg     2,064ms
hybrid_search.vector_leg     12,344ms   <- 11.7s of this was the one-time
                                            SentenceTransformer model load,
                                            not per-request cost
hybrid_search.total          13,938ms
chat.time_to_first_token     34,417ms   <- includes the 13.9s retrieval
                                            above + ~20.5s of pure Gemini wait
chat.total_generation         36,562ms
chat.save_assistant_message      521ms
chat.save_citations              143ms
-----------------------------------------
Total (curl, end to end)      38,137ms
```

Once warm (embedding model loaded), retrieval settled to **350-600ms** —
small. The startup import of `torch`/`sentence-transformers` alone took
~20-34 seconds (separate from any per-request cost, but explains why the
very first request after a `--reload` restart always felt catastrophically
slow — every dev-loop file save paid this again).

## Fixes applied and verified

All verified against the real running server (`backend/venv`), not just
code review. Server still points at remote Supabase (see "Local Postgres/
Qdrant cutover" below for why) — every fix here is independent of that.

### 1. Event-loop-blocking DB/file calls (severity: high)

`chat.py`'s `stream_chat_response`, `security.py`'s `get_current_user`
(a dependency on every authenticated route), and `documents.py`'s
`upload_document` were all `async def` making blocking synchronous
SQLAlchemy/file-I/O calls directly on the event loop. Since local dev runs
single-process/single-worker (`uvicorn --reload`), every one of those calls
froze the *entire server* for *every concurrent user*, not just the
requesting one — the most severe class of bug found.

**Fix**: extracted each blocking call into a small named helper function
and wrapped it in `starlette.concurrency.run_in_threadpool`.

**Verification**: fired two concurrent chat streams (conversations 4 and
5) and, while both were mid-flight doing their DB bookkeeping, hit `GET /`
15 times at 400ms intervals:

```
probe  1: 101ms   probe  6: 63ms    probe 11: 79ms
probe  2: 117ms   probe  7: 70ms    probe 12: 69ms
probe  3: 73ms    probe  8: 71ms    probe 13: 69ms
probe  4: 71ms    probe  9: 71ms    probe 14: 64ms
probe  5: 81ms    probe 10: 67ms    probe 15: 69ms
```

Flat 60-120ms the whole time — no stalls. The two conversations' phase logs
also interleaved in time rather than one blocking the other. Both streams
completed successfully with real generated content.

### 2. SQLAlchemy connection pool tuning (severity: medium)

`database.py`'s `create_engine(...)` had zero pool configuration for
non-SQLite URLs — `pool_pre_ping=False` by default means a connection
silently dropped by a remote Postgres (or an intervening proxy) after
sitting idle shows up as an intermittent failed/slow query instead of a
clean reconnect. Added `pool_pre_ping=True`, `pool_recycle=1800`,
`pool_size=10`, `max_overflow=20` for non-SQLite URLs.

### 3. `SupabaseDBService` connection pooling (severity: medium, prod-live)

Previously held a single shared raw `psycopg2` connection for the whole
process — not safe for concurrent use, so concurrent vector searches could
contend or interfere on it. Replaced with a `psycopg2.pool.ThreadedConnectionPool`
(borrow/return per operation), with public method signatures unchanged.

**Bug found and fixed during verification, not anticipated in the plan**:
the initial lock-free `if cls._pool is None: ...` implementation was a
classic check-then-set race. An 8-thread concurrency smoke test caught it
immediately — the log showed **8 separate pools created** instead of 1,
each opening its own connections, 7 of them silently leaked:

```
Created Supabase PostgreSQL connection pool (pgvector).   [x8]
```

Added a `threading.Lock` with double-checked locking around pool creation.
Re-ran the same 8-thread test: exactly 1 "Created ... pool" log line, all 8
concurrent `health_check()` calls returned correctly
(`{'status': 'healthy', 'vector_rows': 1145, ...}`).

### 4. Eager embedding-model warm-up (severity: medium)

The local `SentenceTransformer` model was loaded lazily on the first
`get_embeddings()` call — meaning the first chat request after every
process start (including every `--reload` restart in dev) paid the
multi-second load cost inline as part of that user-facing request. Added
`EmbeddingsService.warm_up()`, called from a new `lifespan` handler in
`main.py` (replacing the previous import-time-only startup logic) via
`run_in_threadpool`.

**Verified**: server log now shows the model loading during startup
(`EmbeddingsService: local model warmed up at startup.`), ~10s after
Alembic migrations, before the app starts accepting requests — confirmed
the very next request (`GET /`) returned in 6ms, and the first real chat
query's retrieval phase no longer includes any model-load cost.

### 5. Admin analytics query consolidation (severity: low)

`get_document_analytics` and `get_conversation_analytics` each issued
several sequential, independent round trips. Combined `total_documents`/
`total_size_bytes` into one query (both against `Document`), and
`total_feedbacks`/`positive_feedbacks`/`negative_feedbacks` into one
conditional-aggregation query (`func.count(...).filter(...)`) instead of
three. Document analytics: 5→4 queries. Conversation analytics: 5→3
queries. Verified both endpoints still return correct data:
`{"total_documents":17,"total_chunks":1145,...}` and
`{"total_conversations":5,"total_messages":27,...}`.

### 6. Permanent request-timing instrumentation (new capability)

`backend/app/core/timing.py` (a `phase()` context manager) + a global
request-timing middleware in `main.py` + named phases through the chat and
`hybrid_search` hot paths. This didn't exist before this pass — there was
no way to get real numbers without adding it. Kept permanently (negligible
overhead) rather than ripped out after use, so future latency regressions
are visible in logs immediately instead of requiring fresh instrumentation
each time.

## Local Postgres/Qdrant cutover — attempted, reverted

The original plan was to switch local dev off remote Supabase (both the
relational DB and the vector store) onto the already-provisioned local
`docker-compose.yml` Postgres + Qdrant, to eliminate public-internet
round-trip latency. `backend/app/core/config.py` gained the `QDRANT_HOST`/
`QDRANT_PORT` fields this requires (previously missing entirely — would
have crashed on first vector call), but the actual cutover was reverted.

**Why**: Docker Desktop's WSL2 backend is broken on this machine —
`wsl -l -v` shows zero installed distributions, meaning the
`docker-desktop`/`docker-desktop-data` WSL distros Docker needs were never
created. Running `wsl --update` fixed an outdated-kernel warning but did
not fix this. Properly diagnosing further needs admin-elevated PowerShell
(checking Windows optional features), which wasn't available in this
session.

**Why this wasn't worth fighting further**: the baseline measurement above
already answered the question this cutover was meant to answer. Once warm,
`hybrid_search` against remote Supabase takes 350-600ms — genuinely small.
The one-time embedding-model load (11.7s) that inflated the very first
request's numbers is now fixed by the eager warm-up (#4 above), independent
of where the DB lives. Against Gemini's 17-58s, a few hundred milliseconds
of DB round-trip time is noise. If Docker/WSL gets fixed later, `backend/.env`
has the revert documented inline (`VECTOR_DB_BACKEND=supabase`/
`DATABASE_URL` currently point at production Supabase, with a comment
explaining what to change to re-attempt the cutover).

## What's still open

1. **Gemini latency itself** (see "Headline finding" above) — needs
   `OPENAI_API_KEY`/`ANTHROPIC_API_KEY` to actually enable fallback, plus an
   explicit `request_options` timeout on the Gemini call. This is the
   biggest remaining lever by a wide margin.
2. **Local Postgres/Qdrant** — blocked on fixing Docker Desktop's WSL2
   backend on this machine (see above). Low priority given the measured
   marginal benefit.
3. Not investigated in this pass: why Gemini's own latency is so variable
   (17-58s across near-identical short prompts) — could be API tier/quota
   throttling, region, or the specific model (`gemini-3.5-flash`). Worth a
   support ticket / API console check with the provider directly.
