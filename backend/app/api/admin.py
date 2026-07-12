from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Dict, Any

from app.core.database import get_db
from app.core.security import consultant_or_above
from app.models.models import User, Document, Chunk, Conversation, Message, Feedback, Collection
from app.schemas.schemas import DocumentAnalytics, ConversationAnalytics, ChunkResponse, CollectionResponse

router = APIRouter(prefix="/api/admin", tags=["admin"])

@router.get("/collections", response_model=List[str])
def list_collections(
    db: Session = Depends(get_db),
    current_user: User = Depends(consultant_or_above)
):
    """
    Backward-compatible endpoint: returns distinct collection names as bare
    strings (this is what the frontend collection picker currently expects
    -- see frontend/lib/api.ts's listCollections()). Kept as-is on purpose;
    full frontend wiring to Collection.id is deferred (see CLAUDE.md).
    """
    # Fetch distinct collection names from documents table
    results = db.query(Document.collection_name).distinct().all()
    collections = [r[0] for r in results]
    if "Default" not in collections:
        collections.append("Default")
    return collections

@router.get("/collections/full", response_model=List[CollectionResponse])
def list_collections_full(
    db: Session = Depends(get_db),
    current_user: User = Depends(consultant_or_above)
):
    """
    Returns the real Collection rows (id, name, embedding_model, etc.) now
    that collections are a first-class table. Additive endpoint -- does not
    replace /collections, which the frontend still consumes as List[str].
    """
    return db.query(Collection).order_by(Collection.name.asc()).all()

@router.get("/analytics/documents", response_model=DocumentAnalytics)
def get_document_analytics(
    db: Session = Depends(get_db),
    current_user: User = Depends(consultant_or_above)
):
    # total_docs/total_size are both against Document -- one round trip
    # instead of two (each extra round trip matters more against a remote
    # DB, see backend/PERFORMANCE_AUDIT.md).
    total_docs, total_size = db.query(func.count(Document.id), func.sum(Document.file_size)).one()
    total_size = total_size or 0
    total_chunks = db.query(Chunk).count()

    # Status count
    status_results = db.query(Document.status, func.count(Document.id)).group_by(Document.status).all()
    status_counts = {status: count for status, count in status_results}
    
    # Collection counts
    coll_results = db.query(Document.collection_name, func.count(Document.id)).group_by(Document.collection_name).all()
    collection_counts = {coll: count for coll, count in coll_results}
    
    return {
        "total_documents": total_docs,
        "total_chunks": total_chunks,
        "total_size_bytes": total_size,
        "status_counts": status_counts,
        "collection_counts": collection_counts
    }

@router.get("/analytics/conversations", response_model=ConversationAnalytics)
def get_conversation_analytics(
    db: Session = Depends(get_db),
    current_user: User = Depends(consultant_or_above)
):
    total_convs = db.query(Conversation).count()
    total_msgs = db.query(Message).count()

    # total/positive/negative feedback counts combined into one conditional
    # aggregation query instead of three (see backend/PERFORMANCE_AUDIT.md).
    total_feedbacks, pos_feedbacks, neg_feedbacks = db.query(
        func.count(Feedback.id),
        func.count(Feedback.id).filter(Feedback.score == 1),
        func.count(Feedback.id).filter(Feedback.score == -1),
    ).one()
    
    return {
        "total_conversations": total_convs,
        "total_messages": total_msgs,
        "total_feedbacks": total_feedbacks,
        "positive_feedbacks": pos_feedbacks,
        "negative_feedbacks": neg_feedbacks
    }

@router.get("/chunks", response_model=List[ChunkResponse])
def get_chunks(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(consultant_or_above)
):
    # Verify document exists
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
        
    chunks = db.query(Chunk).filter(Chunk.document_id == document_id).order_by(Chunk.chunk_index.asc()).all()
    return chunks
