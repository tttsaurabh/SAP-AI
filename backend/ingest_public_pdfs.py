"""
ingest_public_pdfs.py
=====================
Bulk ingestion script — parses every PDF in ../public/, chunks the text,
embeds with sentence-transformers, and upserts to Pinecone (or Qdrant).

Usage:
    cd backend
    .\\venv\\Scripts\\python.exe ingest_public_pdfs.py

Features:
  - Skips already-ingested files (checks SQL DB by filename)
  - Processes each PDF page-by-page to handle very large files (e.g. MDG100.pdf 249MB)
  - Saves progress to ingest_log.txt
  - Falls back gracefully if Pinecone is unreachable
"""

import os
import sys
import time

# Make sure app modules are importable
sys.path.insert(0, os.path.dirname(__file__))

from loguru import logger
from sqlalchemy.orm import Session

# Bootstrap DB and settings
from app.core.config import settings
from app.core.database import SessionLocal, engine
from app.models import models

models.Base.metadata.create_all(bind=engine)

from app.models.models import Document, Chunk
from app.services.parser import DocumentParser
from app.services.chunker import DocumentChunker
from app.services.vector_db import get_vector_backend

# ─────────────────────────────────────────────────────────────────────────────
PUBLIC_DIR = os.path.join(os.path.dirname(__file__), "..", "public")
COLLECTION_NAME = "Default"
LOG_FILE = os.path.join(os.path.dirname(__file__), "ingest_log.txt")
# ─────────────────────────────────────────────────────────────────────────────


def get_db() -> Session:
    db = SessionLocal()
    try:
        return db
    except Exception:
        db.close()
        raise


def already_ingested(db: Session, filename: str) -> bool:
    doc = db.query(Document).filter(
        Document.filename == filename,
        Document.status == "active",
    ).first()
    return doc is not None


def ingest_pdf(db: Session, pdf_path: str, filename: str) -> bool:
    logger.info(f"[START] Ingesting: {filename}")
    t0 = time.time()

    # 1. Parse
    try:
        pages = DocumentParser.parse_file(pdf_path, filename)
    except Exception as e:
        logger.error(f"[SKIP] Parsing failed for {filename}: {e}")
        return False

    if not pages:
        logger.warning(f"[SKIP] No content extracted from {filename}")
        return False

    # 2. Chunk using parent-child ("small-to-big") hierarchical chunking
    # (Phase 8b) -- same DocumentChunker.chunk_document_hierarchical /
    # settings-driven sizes as the interactive upload path in
    # app/api/documents.py's process_document_ingestion, so both entry
    # points share one source of truth instead of drifting (this script
    # previously hardcoded 1200/200 tokens while the upload path used the
    # chunker's 450/80 defaults -- see Phase 5 CLAUDE.md Work Log entry).
    parent_size = settings.PARENT_CHUNK_SIZE_TOKENS
    child_size = settings.CHILD_CHUNK_SIZE_TOKENS
    child_overlap = settings.CHILD_CHUNK_OVERLAP_TOKENS
    parents = DocumentChunker.chunk_document_hierarchical(
        pages, parent_size=parent_size, child_size=child_size, child_overlap=child_overlap
    )
    if not parents:
        logger.warning(f"[SKIP] No chunks generated for {filename}")
        return False

    file_size = os.path.getsize(pdf_path)

    # 3. Create Document record in SQL DB
    db_doc = Document(
        filename=filename,
        file_path=pdf_path,
        file_size=file_size,
        collection_name=COLLECTION_NAME,
        document_type="PDF",
        status="processing",
        total_chunks=0,
        parent_chunk_size=parent_size,
        chunk_size=child_size,
        chunk_overlap=child_overlap,
    )
    db.add(db_doc)
    db.commit()
    db.refresh(db_doc)

    try:
        # 4. Insert parent rows first (flushed to get real chunks.id values
        # before inserting their children, since Chunk.parent_id is a
        # self-FK), then child rows with parent_id set. Only children are
        # collected for the vector upsert below (parents are SQL-only
        # context, never embedded).
        all_children = []
        next_index = 0
        for parent in parents:
            if not parent.get("children"):
                logger.warning(f"Parent chunk produced zero children for {filename}; skipping.")
                continue

            parent_obj = Chunk(
                document_id=db_doc.id,
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
                child["vector_id"] = f"doc{db_doc.id}_chunk{child_index}"
                child_obj = Chunk(
                    document_id=db_doc.id,
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

        # 5. Upsert to vector DB (children only; Supabase/Pinecone/Qdrant
        # based on settings)
        vector_backend = get_vector_backend()
        vector_backend.upsert_chunks(
            collection_name=COLLECTION_NAME,
            document_id=db_doc.id,
            filename=filename,
            chunks=all_children,
        )

        # 6. Mark active
        db_doc.status = "active"
        db_doc.total_chunks = len(all_children)
        db.commit()

        elapsed = time.time() - t0
        msg = (
            f"[DONE] {filename} → {len(pages)} pages, "
            f"{len(parents)} parent chunks, {len(all_children)} child chunks in {elapsed:.1f}s"
        )
        logger.success(msg)
        with open(LOG_FILE, "a", encoding="utf-8") as lf:
            lf.write(msg + "\n")
        return True

    except Exception as e:
        logger.exception(f"[FAILED] {filename}: {e}")
        db_doc.status = "failed"
        db.commit()
        return False


def main():
    if not os.path.isdir(PUBLIC_DIR):
        logger.error(f"Public directory not found: {PUBLIC_DIR}")
        sys.exit(1)

    pdf_files = sorted(
        f for f in os.listdir(PUBLIC_DIR) if f.lower().endswith(".pdf")
    )
    logger.info(f"Found {len(pdf_files)} PDF(s) in: {PUBLIC_DIR}")
    logger.info(f"Vector backend: {settings.VECTOR_DB_BACKEND.upper()}")
    logger.info(f"Pinecone index: {settings.PINECONE_INDEX_NAME}")
    logger.info("─" * 60)

    db = get_db()
    success_count = 0
    skip_count = 0
    fail_count = 0

    for filename in pdf_files:
        if already_ingested(db, filename):
            logger.info(f"[SKIP] Already ingested: {filename}")
            skip_count += 1
            continue

        pdf_path = os.path.join(PUBLIC_DIR, filename)
        ok = ingest_pdf(db, pdf_path, filename)
        if ok:
            success_count += 1
        else:
            fail_count += 1

    db.close()

    logger.info("─" * 60)
    logger.info(
        f"Ingestion complete. "
        f"✅ {success_count} ingested  "
        f"⏭ {skip_count} skipped  "
        f"❌ {fail_count} failed"
    )


if __name__ == "__main__":
    main()
