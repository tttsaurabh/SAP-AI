#!/usr/bin/env python
"""
Test re-ingest pipeline on a single small PDF to validate:
1. Parsing works
2. Chunking works
3. Embedding works at rate-limited pace
4. Supabase vector upsert works
5. Database status updates work

Run with: ./venv/Scripts/python.exe test_single_reingest.py
"""
import os
import sys
import time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from loguru import logger
from sqlalchemy.orm import Session
from app.core.database import SessionLocal, engine
from app.models import models
from app.models.models import Document, Chunk
from app.core.roles import DocumentStatus
from app.services.parser import DocumentParser
from app.services.chunker import DocumentChunker
from app.services.vector_db import get_vector_backend
from app.core.config import settings

logger.enable("app")

# Pick the smallest PDF (enhancing-change-request)
PDF_FILE = r"c:/Users/tttsa/Desktop/SAP AI/public/enhancing-change-request-inbox-with-additional-columns.pdf"
PDF_NAME = os.path.basename(PDF_FILE)

if not os.path.isfile(PDF_FILE):
    print(f"ERROR: {PDF_FILE} not found")
    sys.exit(1)

print(f"\n{'='*70}")
print(f"SINGLE-DOCUMENT RE-INGEST TEST: {PDF_NAME}")
print(f"{'='*70}")
print(f"Settings: EMBEDDING_MODEL={settings.EMBEDDING_MODEL} | DIM={settings.EMBEDDING_DIMENSION}")

# Step 1: Parse
print(f"\n[1/5] PARSING...")
try:
    pages = DocumentParser.parse_file(PDF_FILE, PDF_NAME)
    print(f"  [OK] Parsed {len(pages)} pages")
except Exception as e:
    print(f"  [FAIL] Parse failed: {e}")
    sys.exit(1)

# Step 2: Chunk
print(f"\n[2/5] CHUNKING...")
try:
    parents = DocumentChunker.chunk_document_hierarchical(
        pages,
        parent_size=settings.PARENT_CHUNK_SIZE_TOKENS,
        child_size=settings.CHILD_CHUNK_SIZE_TOKENS,
        child_overlap=settings.CHILD_CHUNK_OVERLAP_TOKENS,
    )
    total_children = sum(len(p.get("children", [])) for p in parents)
    print(f"  [OK] Created {len(parents)} parents, {total_children} children")
except Exception as e:
    print(f"  [FAIL] Chunk failed: {e}")
    sys.exit(1)

# Step 3: Create or update Document record
print(f"\n[3/5] DATABASE...")
db = SessionLocal()
try:
    doc = db.query(Document).filter(Document.filename == PDF_NAME).first()
    if not doc:
        print(f"  Creating new Document record...")
        doc = Document(
            filename=PDF_NAME,
            file_path=PDF_FILE,
            file_size=os.path.getsize(PDF_FILE),
            status=DocumentStatus.PROCESSING,
            collection_name="Default",
            chunk_size=settings.CHILD_CHUNK_SIZE_TOKENS,
            chunk_overlap=settings.CHILD_CHUNK_OVERLAP_TOKENS,
        )
        db.add(doc)
        db.flush()
    else:
        print(f"  Updating existing Document {doc.id}...")
        doc.status = DocumentStatus.PROCESSING
        db.flush()

    doc_id = doc.id
    print(f"  [OK] Document ID={doc_id}")
    db.commit()
except Exception as e:
    db.rollback()
    print(f"  [FAIL] Database failed: {e}")
    sys.exit(1)
finally:
    db.close()

# Step 4: Insert chunks + prepare for embedding
print(f"\n[4/5] EMBEDDING (rate-limited to ~90/min)...")
db = SessionLocal()
try:
    # Delete old chunks
    db.query(Chunk).filter(Chunk.document_id == doc_id).delete()
    db.commit()

    all_children = []
    next_index = 0
    chunk_start = time.time()

    for parent in parents:
        if not parent.get("children"):
            continue
        parent_obj = Chunk(
            document_id=doc_id,
            text=parent["text"],
            chunk_index=next_index,
            page_number=parent["page_number"],
            section_header=parent.get("section_header", ""),
            chunk_metadata=parent.get("chunk_metadata", {}),
            is_parent=True,
        )
        db.add(parent_obj)
        db.flush()
        next_index += 1

        for child in parent["children"]:
            child_index = next_index
            child["vector_id"] = f"doc{doc_id}_chunk{child_index}"
            child_obj = Chunk(
                document_id=doc_id,
                text=child["text"],
                chunk_index=child_index,
                page_number=child.get("page_number", 1),
                section_header=child.get("section_header", ""),
                chunk_metadata=child.get("chunk_metadata", {}),
                vector_id=child["vector_id"],
                parent_id=parent_obj.id,
                is_parent=False,
            )
            db.add(child_obj)
            all_children.append(child)  # Just the dict, not a tuple
            next_index += 1

    db.flush()
    # Populate chunk_id on all children after ORM flush
    for i, child in enumerate(all_children):
        # Re-fetch to get the chunk_id from DB
        chunk_obj = db.query(Chunk).filter(
            Chunk.document_id == doc_id,
            Chunk.vector_id == child["vector_id"]
        ).first()
        if chunk_obj:
            child["chunk_id"] = chunk_obj.id

    db.commit()

    # Embed and upsert
    print(f"  Embedding {len(all_children)} child chunks (with rate limit)...")
    embed_start = time.time()
    vector_backend = get_vector_backend()
    vector_backend.upsert_chunks(
        collection_name="Default",
        document_id=doc_id,
        filename=PDF_NAME,
        chunks=all_children,
    )
    embed_secs = time.time() - embed_start
    print(f"  [OK] Embedded {len(all_children)} chunks in {embed_secs:.1f}s ({len(all_children)/embed_secs:.1f} items/sec)")

    # Mark active
    doc.status = DocumentStatus.ACTIVE
    doc.total_chunks = len(all_children)
    db.commit()

except Exception as e:
    db.rollback()
    print(f"  [FAIL] Embedding/upsert failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
finally:
    db.close()

# Step 5: Verify retrieval
print(f"\n[5/5] RETRIEVAL VERIFICATION...")
db = SessionLocal()
try:
    from app.services.rag_engine import RAGEngine
    chunks = RAGEngine.hybrid_search(db, "Default", "change request", limit=3)
    if chunks:
        print(f"  [OK] Hybrid search returned {len(chunks)} results")
        for i, c in enumerate(chunks, 1):
            print(f"    [{i}] {c['filename']} page {c['page_number']}: {c['text'][:60]}...")
    else:
        print(f"  [FAIL] Hybrid search returned zero results")
        sys.exit(1)
except Exception as e:
    print(f"  [FAIL] Retrieval failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
finally:
    db.close()

print(f"\n{'='*70}")
print(f"SUCCESS! Single-document re-ingest pipeline validated.")
print(f"{'='*70}\n")
