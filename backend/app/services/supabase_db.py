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
from typing import List, Dict, Any, Optional
from loguru import logger
from app.core.config import settings
from app.services.embeddings import EmbeddingsService

try:
    import psycopg2
    import psycopg2.extras
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
    
    _conn = None
    _supabase: Optional["SupabaseClient"] = None

    # ------------------------------------------------------------------ #
    #  Client initialisation                                               #
    # ------------------------------------------------------------------ #

    @classmethod
    def get_connection(cls):
        """Get or create a psycopg2 connection to Supabase PostgreSQL."""
        if cls._conn is None or cls._conn.closed:
            db_url = settings.SUPABASE_DB_URL or settings.DATABASE_URL
            if not db_url or "YOUR_PROJECT_ID" in db_url:
                raise ValueError(
                    "SUPABASE_DB_URL is not configured. "
                    "Set it in .env: postgresql://postgres:PASSWORD@db.PROJECT_ID.supabase.co:5432/postgres"
                )
            if psycopg2 is None:
                raise ImportError("psycopg2-binary not installed. Run: pip install psycopg2-binary")
            
            try:
                cls._conn = psycopg2.connect(db_url)
                cls._conn.autocommit = True
                logger.info("Connected to Supabase PostgreSQL (pgvector).")
            except Exception as e:
                raise ConnectionError(f"Failed to connect to Supabase PostgreSQL: {e}") from e
        return cls._conn

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
        conn = cls.get_connection()
        dim = settings.EMBEDDING_DIMENSION
        table = settings.SUPABASE_VECTOR_TABLE
        with conn.cursor() as cur:
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
        conn = cls.get_connection()
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

        with conn.cursor() as cur:
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
        conn = cls.get_connection()
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
        conn = cls.get_connection()
        table = settings.SUPABASE_VECTOR_TABLE
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
            conn = cls.get_connection()
            table = settings.SUPABASE_VECTOR_TABLE
            with conn.cursor() as cur:
                cur.execute(f"SELECT COUNT(*) FROM {table};")
                count = cur.fetchone()[0]
            return {"status": "healthy", "vector_rows": count, "backend": "supabase_pgvector"}
        except Exception as e:
            return {"status": "error", "message": str(e), "backend": "supabase_pgvector"}
