import os
import shutil
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile, File, Form, status
from sqlalchemy.orm import Session
from typing import List
from loguru import logger

from app.core.config import settings
from app.core.database import get_db, SessionLocal
from app.core.security import admin_only
from app.core.roles import DocumentStatus
from app.models.models import User, Document, Chunk, Collection
from app.schemas.schemas import DocumentResponse
from app.services.parser import DocumentParser
from app.services.chunker import DocumentChunker
from app.services.vector_db import get_vector_backend

router = APIRouter(prefix="/api/documents", tags=["documents"])


def _get_or_create_collection(db: Session, name: str, created_by: int = None) -> Collection:
    """
    Get-or-create a Collection row by name. On first creation, stamp
    embedding_model with the currently configured EMBEDDING_MODEL so later
    uploads into the same collection can be checked for embedding-space
    mismatches (see _ensure_embedding_model_compatible below).
    """
    collection = db.query(Collection).filter(Collection.name == name).first()
    if collection is None:
        collection = Collection(
            name=name,
            created_by=created_by,
            embedding_model=settings.EMBEDDING_MODEL,
        )
        db.add(collection)
        db.commit()
        db.refresh(collection)
    return collection


def _ensure_embedding_model_compatible(collection: Collection):
    """
    Raise a clear error if the collection was first populated with a
    different embedding model than the one currently configured, instead of
    silently mixing embedding spaces in the same vector index/namespace.
    """
    if collection.embedding_model and collection.embedding_model != settings.EMBEDDING_MODEL:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Collection '{collection.name}' was ingested with embedding model "
                f"'{collection.embedding_model}', but the server is currently configured "
                f"with '{settings.EMBEDDING_MODEL}'. Mixing embedding spaces in the same "
                f"collection is not supported -- use a different collection name or "
                f"reconfigure EMBEDDING_MODEL to match."
            ),
        )

@router.get("/", response_model=List[DocumentResponse])
def list_documents(
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_only)
):
    return db.query(Document).order_by(Document.created_at.desc()).all()

def process_document_ingestion(document_id: int, file_path: str, filename: str, collection_name: str) -> None:
    """
    Background task body (invoked via FastAPI `BackgroundTasks`, so it runs
    AFTER the HTTP response for the upload request has already been sent).

    Contains the actual parse -> chunk -> insert-chunks -> vector-upsert ->
    status-update pipeline that used to run synchronously inline in the
    `upload_document` request handler -- this is why large PDFs previously
    took 170-210s per `backend/ingest_log.txt` and blocked the request the
    whole time.

    CRITICAL: this does NOT reuse the request-scoped `Session` from
    `Depends(get_db)` -- that session is closed by the time this function
    runs (the request has already returned). It opens its own session via
    `SessionLocal()` and closes it in a `finally` block, matching the
    "one session per unit of work" pattern `get_db()` itself follows.
    """
    db = SessionLocal()
    try:
        db_doc = db.query(Document).filter(Document.id == document_id).first()
        if not db_doc:
            logger.error(f"process_document_ingestion: document {document_id} not found (deleted before background task ran?)")
            return

        # 1. Parse File
        pages = DocumentParser.parse_file(file_path, filename)

        # 2. Chunk File
        chunks = DocumentChunker.chunk_document(pages)

        # Generate vector IDs here -- single source of truth, reused both for
        # the vector store upsert and the Chunk.vector_id column, instead of
        # each vector backend independently deriving its own id formula.
        for c in chunks:
            c["vector_id"] = f"doc{document_id}_chunk{c['chunk_index']}"

        # 3. Insert chunks in SQL
        for c in chunks:
            chunk_obj = Chunk(
                document_id=document_id,
                text=c["text"],
                chunk_index=c["chunk_index"],
                page_number=c["page_number"],
                section_header=c["section_header"],
                chunk_metadata=c["chunk_metadata"],
                vector_id=c["vector_id"]
            )
            db.add(chunk_obj)
        db.commit()

        # 4. Insert in Vector Database (Pinecone or Qdrant based on config)
        vector_backend = get_vector_backend()
        vector_backend.upsert_chunks(
            collection_name=collection_name,
            document_id=document_id,
            filename=filename,
            chunks=chunks
        )

        # 5. Update document status
        db_doc.status = DocumentStatus.ACTIVE
        db_doc.total_chunks = len(chunks)
        db_doc.error_message = None
        db.commit()
        logger.info(f"Background ingestion complete for document {document_id} ({filename}): {len(chunks)} chunks")

    except Exception as e:
        logger.exception(f"Background ingestion failed for document {document_id} ({filename})")
        try:
            db_doc = db.query(Document).filter(Document.id == document_id).first()
            if db_doc:
                db_doc.status = DocumentStatus.FAILED
                # Cap length -- an unbounded exception string (e.g. a huge
                # stack trace embedded in a library's error message)
                # shouldn't blow up the column/response payload.
                db_doc.error_message = str(e)[:2000]
                db.commit()
        except Exception:
            logger.exception(f"Failed to record failure status for document {document_id}")
    finally:
        db.close()


@router.post("/upload", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    collection_name: str = Form("Default"),
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_only)
):
    logger.info(f"User {current_user.email} uploading document: {file.filename} to collection '{collection_name}'")

    # Create local path
    upload_dir = "./uploads"
    os.makedirs(upload_dir, exist_ok=True)
    file_path = os.path.join(upload_dir, file.filename)

    # Save file
    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        logger.error(f"Failed to write file to disk: {str(e)}")
        raise HTTPException(status_code=500, detail=f"File save error: {str(e)}")

    file_size = os.path.getsize(file_path)
    ext = os.path.splitext(file.filename)[1].lower()

    # 0. Get-or-create the Collection row for this collection name, and make
    # sure the currently configured embedding model matches whatever this
    # collection was first ingested with (fail loud instead of silently
    # mixing embedding spaces in one vector index/namespace).
    collection = _get_or_create_collection(db, collection_name, created_by=current_user.id)
    _ensure_embedding_model_compatible(collection)

    # 1. Create Document in DB (fast path) -- parse/chunk/embed/upsert are
    # deferred to a BackgroundTask (process_document_ingestion below) so
    # this request returns immediately instead of blocking for the 170-210s
    # a large PDF can take (see backend/ingest_log.txt). The document is
    # visible in the UI right away with status=processing; the admin page
    # polls for the status transition to active/failed (see
    # frontend/app/admin/page.tsx).
    db_doc = Document(
        filename=file.filename,
        file_path=file_path,
        file_size=file_size,
        collection_name=collection_name,
        collection_id=collection.id,
        document_type=ext.replace(".", "").upper(),
        status=DocumentStatus.PROCESSING,
        total_chunks=0
    )
    db.add(db_doc)
    db.commit()
    db.refresh(db_doc)

    background_tasks.add_task(
        process_document_ingestion,
        document_id=db_doc.id,
        file_path=file_path,
        filename=file.filename,
        collection_name=collection_name,
    )

    return db_doc

@router.delete("/{doc_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(
    doc_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_only)
):
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
        
    # Delete file from local storage
    if os.path.exists(doc.file_path):
        try:
            os.remove(doc.file_path)
        except Exception as e:
            logger.warning(f"Could not remove local file {doc.file_path}: {str(e)}")
            
    # Delete from Vector DB (Pinecone or Qdrant based on config)
    vector_backend = get_vector_backend()
    vector_backend.delete_document_vectors(doc.collection_name, doc.id)
    
    # Delete from SQL (cascades to Chunks table)
    db.delete(doc)
    db.commit()
    return None
