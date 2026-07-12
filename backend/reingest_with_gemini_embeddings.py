"""
reingest_with_gemini_embeddings.py
===================================
Run this ONCE after switching EMBEDDING_MODEL from local sentence-transformers
(384 dims) to Gemini text-embedding-004 (768 dims).

What it does:
  1. Drops the old document_vectors table (wrong dimension)
  2. Recreates it with 768-dim embeddings
  3. Marks all active Documents in SQL DB as needing re-ingest
  4. Re-ingests every document from its original file path (PDFs in /public/)
     using the new Gemini embeddings

Usage:
    cd backend
    .\\venv\\Scripts\\python.exe reingest_with_gemini_embeddings.py
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))

from loguru import logger
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import SessionLocal, engine
from app.models import models
models.Base.metadata.create_all(bind=engine)
from app.models.models import Document, Chunk
from app.core.roles import DocumentStatus
from app.services.parser import DocumentParser
from app.services.chunker import DocumentChunker
from app.services.vector_db import get_vector_backend
from app.services.supabase_db import SupabaseDBService

LOG_FILE = os.path.join(os.path.dirname(__file__), "reingest_log.txt")

# ─────────────────────────────────────────────────────────────────────────────

def drop_and_recreate_vector_table():
    """
    Drop the existing document_vectors table (wrong 384-dim embeddings)
    and recreate it fresh with 768 dims for Gemini text-embedding-004.
    """
    table = settings.SUPABASE_VECTOR_TABLE
    dim = settings.EMBEDDING_DIMENSION
    logger.info(f"Dropping and recreating '{table}' with {dim}-dim embeddings...")
    with SupabaseDBService._borrowed_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(f"DROP TABLE IF EXISTS {table} CASCADE;")
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
            cur.execute(f"""
                CREATE TABLE {table} (
                    id              BIGSERIAL PRIMARY KEY,
                    vector_id       TEXT UNIQUE NOT NULL,
                    document_id     INTEGER NOT NULL,
                    filename        TEXT NOT NULL,
                    collection_name TEXT NOT NULL,
                    chunk_text      TEXT NOT NULL,
                    page_number     INTEGER DEFAULT 1,
                    section_header  TEXT DEFAULT '',
                    embedding       VECTOR({dim}),
                    created_at      TIMESTAMPTZ DEFAULT NOW(),
                    chunk_id        INTEGER,
                    chunk_index     INTEGER
                );
            """)
            # Create HNSW index for fast ANN search
            cur.execute(f"""
                CREATE INDEX IF NOT EXISTS {table}_embedding_idx
                ON {table}
                USING hnsw (embedding vector_cosine_ops)
                WITH (m = 16, ef_construction = 64);
            """)
    logger.success(f"Table '{table}' recreated with {dim}-dim vector column + HNSW index.")


def reset_documents_for_reingest(db: Session):
    """Mark all active/failed documents as 'processing' so ingest_document processes them."""
    count = db.query(Document).filter(Document.status.in_([DocumentStatus.ACTIVE, DocumentStatus.FAILED])).update(
        {"status": DocumentStatus.PROCESSING}, synchronize_session=False
    )
    # Also delete old chunk rows (they'll be recreated during re-ingest)
    db.query(Chunk).delete(synchronize_session=False)
    db.commit()
    logger.info(f"Reset {count} documents to 'processing' and cleared all chunk rows.")
    return count


def ingest_document(db: Session, doc: Document) -> bool:
    """Re-ingest a single document."""
    filename = doc.filename
    file_path = doc.file_path

    # Try original file path first, then look in /public/
    if not file_path or not os.path.isfile(file_path):
        public_dir = os.path.join(os.path.dirname(__file__), "..", "public")
        candidate = os.path.join(public_dir, filename)
        if os.path.isfile(candidate):
            file_path = candidate
        else:
            # Try uploads dir
            uploads_dir = settings.UPLOADS_DIR
            candidate2 = os.path.join(uploads_dir, filename)
            if os.path.isfile(candidate2):
                file_path = candidate2
            else:
                logger.warning(f"[SKIP] File not found for '{filename}' (tried multiple locations)")
                doc.status = DocumentStatus.FAILED
                db.commit()
                return False

    logger.info(f"[START] Re-ingesting: {filename}")
    t0 = time.time()

    # 1. Parse
    try:
        pages = DocumentParser.parse_file(file_path, filename)
    except Exception as e:
        logger.error(f"[FAIL] Parsing failed for {filename}: {e}")
        doc.status = DocumentStatus.FAILED
        db.commit()
        return False

    if not pages:
        logger.warning(f"[SKIP] No content from {filename}")
        doc.status = DocumentStatus.FAILED
        db.commit()
        return False

    # 2. Chunk
    parent_size = settings.PARENT_CHUNK_SIZE_TOKENS
    child_size = settings.CHILD_CHUNK_SIZE_TOKENS
    child_overlap = settings.CHILD_CHUNK_OVERLAP_TOKENS
    parents = DocumentChunker.chunk_document_hierarchical(
        pages, parent_size=parent_size, child_size=child_size, child_overlap=child_overlap
    )
    if not parents:
        logger.warning(f"[SKIP] No chunks for {filename}")
        doc.status = DocumentStatus.FAILED
        db.commit()
        return False

    # 3. Update document record
    doc.file_path = file_path
    doc.file_size = os.path.getsize(file_path)
    doc.parent_chunk_size = parent_size
    doc.chunk_size = child_size
    doc.chunk_overlap = child_overlap
    doc.status = DocumentStatus.PROCESSING
    db.commit()

    try:
        # 4. Insert parent + child chunks
        all_children = []
        next_index = 0
        for parent in parents:
            if not parent.get("children"):
                continue
            parent_obj = Chunk(
                document_id=doc.id,
                text=parent["text"],
                chunk_index=next_index,
                page_number=parent["page_number"],
                section_header=parent["section_header"],
                chunk_metadata=parent["chunk_metadata"],
                is_parent=True,
            )
            db.add(parent_obj)
            db.flush()
            next_index += 1

            pending = []
            for child in parent["children"]:
                child_index = next_index
                child["vector_id"] = f"doc{doc.id}_chunk{child_index}"
                child_obj = Chunk(
                    document_id=doc.id,
                    text=child["text"],
                    chunk_index=child_index,
                    page_number=child["page_number"],
                    section_header=child["section_header"],
                    chunk_metadata=child["chunk_metadata"],
                    vector_id=child["vector_id"],
                    parent_id=parent_obj.id,
                    is_parent=False,
                )
                db.add(child_obj)
                pending.append((child, child_obj))
                next_index += 1

            db.flush()
            for child, child_obj in pending:
                child["chunk_id"] = child_obj.id
                all_children.append(child)

        db.commit()

        # 5. Upsert to vector DB with NEW Gemini embeddings
        vector_backend = get_vector_backend()
        vector_backend.upsert_chunks(
            collection_name=doc.collection_name,
            document_id=doc.id,
            filename=filename,
            chunks=all_children,
        )

        # 6. Mark active
        doc.status = DocumentStatus.ACTIVE
        doc.total_chunks = len(all_children)
        db.commit()

        elapsed = time.time() - t0
        msg = (
            f"[DONE] {filename} → {len(pages)} pages, "
            f"{len(parents)} parents, {len(all_children)} child chunks in {elapsed:.1f}s"
        )
        logger.success(msg)
        with open(LOG_FILE, "a", encoding="utf-8") as lf:
            lf.write(msg + "\n")
        return True

    except Exception as e:
        logger.exception(f"[FAIL] {filename}: {e}")
        doc.status = DocumentStatus.FAILED
        db.commit()
        return False


def main():
    logger.info("=" * 70)
    logger.info("RE-INGESTION SCRIPT: Rebuild vectors with configured embedding model")
    logger.info(f"EMBEDDING_MODEL    : {settings.EMBEDDING_MODEL}")
    logger.info(f"EMBEDDING_DIMENSION: {settings.EMBEDDING_DIMENSION}")
    logger.info(f"GEMINI_API_KEY set : {'YES' if settings.GEMINI_API_KEY else 'NO'}")
    logger.info("=" * 70)

    if not settings.GEMINI_API_KEY and not settings.EMBEDDING_MODEL.startswith("local:"):
        logger.error("GEMINI_API_KEY is not set! Gemini embeddings will fail.")
        sys.exit(1)

    # Step 1: Drop old vector table and recreate with 768 dims
    drop_and_recreate_vector_table()

    # Step 2: Reset all documents for re-ingestion
    db = SessionLocal()
    try:
        total_docs = reset_documents_for_reingest(db)
        if total_docs == 0:
            logger.warning("No documents found to re-ingest. Upload documents first.")
            return

        docs = db.query(Document).filter(Document.status == DocumentStatus.PROCESSING).all()
        logger.info(f"Re-ingesting {len(docs)} documents...")
        logger.info("-" * 70)

        success_count = 0
        fail_count = 0

        for doc in docs:
            ok = ingest_document(db, doc)
            if ok:
                success_count += 1
            else:
                fail_count += 1

    finally:
        db.close()

    logger.info("=" * 70)
    logger.success(
        f"Re-ingestion complete: ✅ {success_count} succeeded  ❌ {fail_count} failed"
    )
    logger.info(f"Log saved to: {LOG_FILE}")


if __name__ == "__main__":
    main()
