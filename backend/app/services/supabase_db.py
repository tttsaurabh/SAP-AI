"""
SupabaseDBService — pgvector-backed vector store using Supabase PostgreSQL.

Implements the same interface as PineconeDBService and VectorDBService:
  - upsert_chunks()
  - search_similarity()
  - delete_document_vectors()

Requires:
  - pgvector extension enabled in Supabase (run supabase_setup.sql once)
  - supabase>=2.3.0 and psycopg2-binary in requirements.txt
  - SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, SUPABASE_DB_URL in .env
"""

import time
import threading
from contextlib import contextmanager
from typing import List, Dict, Any, Optional
from loguru import logger
from app.core.config import settings
from app.services.embeddings import EmbeddingsService

try:
    import psycopg2
    import psycopg2.extras
    import psycopg2.pool
except ImportError:
    psycopg2 = None

try:
    from supabase import create_client, Client as SupabaseClient
except ImportError:
    create_client = None
    SupabaseClient = None


class SupabaseDBService:
    """
    Vector store backed by Supabase PostgreSQL + pgvector extension.
    
    Architecture:
    - Uses psycopg2 directly for vector upsert/search (pgvector SQL)
    - Uses Supabase Python SDK for row-level operations if needed
    - Table: document_vectors (created via supabase_setup.sql)
    """
    
    _pool: Optional["psycopg2.pool.ThreadedConnectionPool"] = None
    _pool_lock = threading.Lock()
    _supabase: Optional["SupabaseClient"] = None

    # ------------------------------------------------------------------ #
    #  Client initialisation                                               #
    # ------------------------------------------------------------------ #

    @classmethod
    def _get_pool(cls) -> "psycopg2.pool.ThreadedConnectionPool":
        """
        Get or create the process-wide psycopg2 connection pool to Supabase
        PostgreSQL. Previously this held a single shared raw connection
        (`_conn`) reused across every call/thread -- psycopg2 connections
        aren't safe for concurrent use, so concurrent vector searches could
        contend or interfere on that one connection. A small pool removes
        that contention without changing any public method's behavior (see
        backend/PERFORMANCE_AUDIT.md).

        Guarded by a lock: the plain `if cls._pool is None` check-then-set
        below is a classic race under concurrent first callers -- a
        concurrency smoke test caught 8 threads each independently seeing
        `None` and creating their own pool, leaking 7 of them (and their
        open connections). The lock makes pool creation happen exactly
        once.
        """
        if cls._pool is None:
            with cls._pool_lock:
                if cls._pool is None:  # re-check: another thread may have won the race
                    db_url = settings.SUPABASE_DB_URL or settings.DATABASE_URL
                    if not db_url or "YOUR_PROJECT_ID" in db_url:
                        raise ValueError(
                            "SUPABASE_DB_URL is not configured. "
                            "Set it in .env: postgresql://postgres:PASSWORD@db.PROJECT_ID.supabase.co:5432/postgres"
                        )
                    if psycopg2 is None:
                        raise ImportError("psycopg2-binary not installed. Run: pip install psycopg2-binary")

                    try:
                        cls._pool = psycopg2.pool.ThreadedConnectionPool(2, 10, dsn=db_url)
                        logger.info("Created Supabase PostgreSQL connection pool (pgvector).")
                    except Exception as e:
                        raise ConnectionError(f"Failed to connect to Supabase PostgreSQL: {e}") from e
        return cls._pool

    @classmethod
    @contextmanager
    def _borrowed_connection(cls):
        """Borrow a pooled connection for the duration of one operation, then return it."""
        pool = cls._get_pool()
        conn = pool.getconn()
        conn.autocommit = True
        try:
            yield conn
        finally:
            pool.putconn(conn)

    @classmethod
    def get_supabase_client(cls) -> "SupabaseClient":
        """Get or create a Supabase SDK client (for REST API operations)."""
        if cls._supabase is None:
            if create_client is None:
                raise ImportError("supabase package not installed. Run: pip install supabase>=2.3.0")
            url = settings.SUPABASE_URL
            key = settings.SUPABASE_SERVICE_ROLE_KEY
            if not url or "YOUR_PROJECT_ID" in url:
                raise ValueError("SUPABASE_URL is not configured in .env")
            if not key or key == "YOUR_SUPABASE_SERVICE_ROLE_KEY":
                raise ValueError("SUPABASE_SERVICE_ROLE_KEY is not configured in .env")
            cls._supabase = create_client(url, key)
            logger.info("Supabase SDK client initialised.")
        return cls._supabase

    @classmethod
    def ensure_table_exists(cls):
        """
        Create document_vectors table with pgvector if it doesn't exist.
        Run supabase_setup.sql in Supabase SQL Editor for proper index setup.
        """
        dim = settings.EMBEDDING_DIMENSION
        table = settings.SUPABASE_VECTOR_TABLE
        with cls._borrowed_connection() as conn, conn.cursor() as cur:
            # Enable pgvector extension
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
            # Create vectors table
            cur.execute(f"""
                CREATE TABLE IF NOT EXISTS {table} (
                    id              BIGSERIAL PRIMARY KEY,
                    vector_id       TEXT UNIQUE NOT NULL,
                    document_id     INTEGER NOT NULL,
                    filename        TEXT NOT NULL,
                    collection_name TEXT NOT NULL,
                    chunk_text      TEXT NOT NULL,
                    page_number     INTEGER DEFAULT 1,
                    section_header  TEXT DEFAULT '',
                    embedding       VECTOR({dim}),
                    created_at      TIMESTAMPTZ DEFAULT NOW()
                );
            """)
            # Idempotently alter table to add columns for parent-child tracking and caching
            cur.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS chunk_id INTEGER;")
            cur.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS chunk_index INTEGER;")
            logger.info(f"Ensured table '{table}' exists and is updated in Supabase (dim={dim}).")

    # ------------------------------------------------------------------ #
    #  Upsert chunks                                                       #
    # ------------------------------------------------------------------ #

    @classmethod
    def upsert_chunks(
        cls,
        collection_name: str,
        document_id: int,
        filename: str,
        chunks: List[Dict[str, Any]],
        batch_size: int = 50,
    ):
        """
        Embeds chunk texts and upserts them as pgvector rows in Supabase.
        Uses INSERT ... ON CONFLICT (vector_id) DO UPDATE for idempotent upserts.
        """
        cls.ensure_table_exists()
        table = settings.SUPABASE_VECTOR_TABLE

        texts = [c["text"] for c in chunks]
        embeddings = EmbeddingsService.get_embeddings(texts)

        rows = []
        for i, chunk in enumerate(chunks):
            vector_id = (
                chunk.get("vector_id")
                or f"doc{document_id}_chunk{chunk['chunk_index']}"
            )
            rows.append((
                vector_id,
                document_id,
                filename,
                collection_name,
                chunk["text"],
                chunk.get("page_number", 1),
                chunk.get("section_header", ""),
                embeddings[i],   # list[float] — adapts automatically
                chunk.get("chunk_id"),
                chunk.get("chunk_index"),
            ))

        upsert_sql = f"""
            INSERT INTO {table}
                (vector_id, document_id, filename, collection_name,
                 chunk_text, page_number, section_header, embedding, chunk_id, chunk_index)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s::vector, %s, %s)
            ON CONFLICT (vector_id) DO UPDATE SET
                chunk_text      = EXCLUDED.chunk_text,
                embedding       = EXCLUDED.embedding,
                page_number     = EXCLUDED.page_number,
                section_header  = EXCLUDED.section_header,
                collection_name = EXCLUDED.collection_name,
                chunk_id        = EXCLUDED.chunk_id,
                chunk_index     = EXCLUDED.chunk_index;
        """

        with cls._borrowed_connection() as conn, conn.cursor() as cur:
            for start in range(0, len(rows), batch_size):
                batch = rows[start : start + batch_size]
                psycopg2.extras.execute_batch(cur, upsert_sql, batch)
                logger.info(
                    f"Upserted batch {start // batch_size + 1} "
                    f"({len(batch)} vectors) into Supabase '{table}'."
                )

        logger.info(
            f"Upserted {len(rows)} total vectors for document '{filename}' "
            f"into Supabase collection '{collection_name}'."
        )

    # ------------------------------------------------------------------ #
    #  Similarity search                                                   #
    # ------------------------------------------------------------------ #

    @classmethod
    def search_similarity(
        cls,
        collection_name: str,
        query: str,
        limit: int = 5,
        document_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Performs cosine similarity search using pgvector <=> operator.
        Filters by collection_name and optionally by document_id.
        """
        table = settings.SUPABASE_VECTOR_TABLE

        query_vector = EmbeddingsService.get_embeddings(query)[0]
        # Format as pgvector literal: [0.1, 0.2, ...]
        vec_literal = "[" + ",".join(str(v) for v in query_vector) + "]"

        if document_id is not None:
            sql = f"""
                SELECT
                    vector_id, document_id, filename, collection_name,
                    chunk_text, page_number, section_header, chunk_id, chunk_index,
                    1 - (embedding <=> %s::vector) AS score
                FROM {table}
                WHERE collection_name = %s
                  AND document_id = %s
                ORDER BY embedding <=> %s::vector
                LIMIT %s;
            """
            params = (vec_literal, collection_name, document_id, vec_literal, limit)
        else:
            sql = f"""
                SELECT
                    vector_id, document_id, filename, collection_name,
                    chunk_text, page_number, section_header, chunk_id, chunk_index,
                    1 - (embedding <=> %s::vector) AS score
                FROM {table}
                WHERE collection_name = %s
                ORDER BY embedding <=> %s::vector
                LIMIT %s;
            """
            params = (vec_literal, collection_name, vec_literal, limit)

        with cls._borrowed_connection() as conn:
            try:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    cur.execute(sql, params)
                    rows = cur.fetchall()

                results = []
                for row in rows:
                    results.append({
                        "score": float(row["score"]),
                        "text": row["chunk_text"],
                        "document_id": row["document_id"],
                        "filename": row["filename"],
                        "page_number": row["page_number"],
                        "section_header": row["section_header"],
                        "collection_name": row["collection_name"],
                        "chunk_id": row.get("chunk_id"),
                        "chunk_index": row.get("chunk_index"),
                    })

                logger.info(
                    f"Supabase pgvector search in '{collection_name}' "
                    f"returned {len(results)} results."
                )
                return results

            except Exception as e:
                logger.error(f"Supabase pgvector search failed: {e}")
                return []

    # ------------------------------------------------------------------ #
    #  Delete document vectors                                             #
    # ------------------------------------------------------------------ #

    @classmethod
    def delete_document_vectors(cls, collection_name: str, document_id: int):
        """
        Deletes all vector rows for a given document_id from Supabase.
        """
        table = settings.SUPABASE_VECTOR_TABLE
        with cls._borrowed_connection() as conn:
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        f"DELETE FROM {table} WHERE document_id = %s AND collection_name = %s;",
                        (document_id, collection_name),
                    )
                logger.info(
                    f"Deleted Supabase vectors for document_id={document_id} "
                    f"in collection '{collection_name}'."
                )
            except Exception as e:
                logger.error(f"Supabase vector delete failed: {e}")

    # ------------------------------------------------------------------ #
    #  Health check                                                        #
    # ------------------------------------------------------------------ #

    @classmethod
    def health_check(cls) -> Dict[str, Any]:
        """Returns connection status and row count for monitoring."""
        try:
            table = settings.SUPABASE_VECTOR_TABLE
            with cls._borrowed_connection() as conn, conn.cursor() as cur:
                cur.execute(f"SELECT COUNT(*) FROM {table};")
                count = cur.fetchone()[0]
            return {"status": "healthy", "vector_rows": count, "backend": "supabase_pgvector"}
        except Exception as e:
            return {"status": "error", "message": str(e), "backend": "supabase_pgvector"}
