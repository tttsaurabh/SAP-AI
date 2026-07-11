from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Dict, Any

from app.core.database import get_db
from app.core.security import admin_only
from app.models.models import User, Document, Chunk, Conversation, Message, Feedback
from app.schemas.schemas import DocumentAnalytics, ConversationAnalytics, ChunkResponse

router = APIRouter(prefix="/api/admin", tags=["admin"])

@router.get("/collections", response_model=List[str])
def list_collections(
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_only)
):
    # Fetch distinct collection names from documents table
    results = db.query(Document.collection_name).distinct().all()
    collections = [r[0] for r in results]
    if "Default" not in collections:
        collections.append("Default")
    return collections

@router.get("/analytics/documents", response_model=DocumentAnalytics)
def get_document_analytics(
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_only)
):
    total_docs = db.query(Document).count()
    total_chunks = db.query(Chunk).count()
    total_size = db.query(func.sum(Document.file_size)).scalar() or 0
    
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
    current_user: User = Depends(admin_only)
):
    total_convs = db.query(Conversation).count()
    total_msgs = db.query(Message).count()
    total_feedbacks = db.query(Feedback).count()
    
    pos_feedbacks = db.query(Feedback).filter(Feedback.score == 1).count()
    neg_feedbacks = db.query(Feedback).filter(Feedback.score == -1).count()
    
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
    current_user: User = Depends(admin_only)
):
    # Verify document exists
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
        
    chunks = db.query(Chunk).filter(Chunk.document_id == document_id).order_by(Chunk.chunk_index.asc()).all()
    return chunks
