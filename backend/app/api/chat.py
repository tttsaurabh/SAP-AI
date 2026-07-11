import json
import asyncio
import re
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from typing import List, Dict, Any

from app.core.database import get_db
from app.core.security import any_authenticated
from app.models.models import User, Conversation, Message, Feedback
from app.schemas.schemas import ConversationResponse, ConversationDetail, MessageResponse, FeedbackCreate, FeedbackResponse
from app.services.rag_engine import RAGEngine

router = APIRouter(prefix="/api/chat", tags=["chat"])

@router.get("/conversations", response_model=List[ConversationResponse])
def get_conversations(
    db: Session = Depends(get_db),
    current_user: User = Depends(any_authenticated)
):
    return db.query(Conversation).filter(Conversation.user_id == current_user.id).order_by(Conversation.updated_at.desc()).all()

@router.post("/conversations", response_model=ConversationResponse)
def create_conversation(
    title: str = "New Conversation",
    db: Session = Depends(get_db),
    current_user: User = Depends(any_authenticated)
):
    conv = Conversation(user_id=current_user.id, title=title)
    db.add(conv)
    db.commit()
    db.refresh(conv)
    return conv

@router.get("/conversations/{conv_id}", response_model=ConversationDetail)
def get_conversation_details(
    conv_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(any_authenticated)
):
    conv = db.query(Conversation).filter(Conversation.id == conv_id).first()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    if conv.user_id != current_user.id and current_user.role != "Super Admin":
        raise HTTPException(status_code=403, detail="Access denied")
    return conv

@router.delete("/conversations/{conv_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_conversation(
    conv_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(any_authenticated)
):
    conv = db.query(Conversation).filter(Conversation.id == conv_id).first()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    if conv.user_id != current_user.id and current_user.role != "Super Admin":
        raise HTTPException(status_code=403, detail="Access denied")
    db.delete(conv)
    db.commit()
    return None

@router.post("/feedback", response_model=FeedbackResponse)
def give_feedback(
    feedback_in: FeedbackCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(any_authenticated)
):
    # Verify message exists
    msg = db.query(Message).filter(Message.id == feedback_in.message_id).first()
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found")
        
    # Check if feedback already exists
    existing = db.query(Feedback).filter(Feedback.message_id == feedback_in.message_id).first()
    if existing:
        existing.score = feedback_in.score
        existing.comments = feedback_in.comments
        db.commit()
        db.refresh(existing)
        return existing
        
    feedback = Feedback(
        message_id=feedback_in.message_id,
        score=feedback_in.score,
        comments=feedback_in.comments
    )
    db.add(feedback)
    db.commit()
    db.refresh(feedback)
    return feedback

@router.get("/conversations/{conv_id}/stream")
async def stream_chat_response(
    conv_id: int,
    query: str,
    collection: str = "Default",
    db: Session = Depends(get_db),
    current_user: User = Depends(any_authenticated)
):
    # Verify conversation
    conv = db.query(Conversation).filter(Conversation.id == conv_id).first()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
        
    # Save user message
    user_msg = Message(conversation_id=conv_id, role="user", content=query, citations=[])
    db.add(user_msg)
    db.commit()
    db.refresh(user_msg)
    
    # Retrieve history
    history = []
    messages = db.query(Message).filter(Message.conversation_id == conv_id).order_by(Message.created_at.asc()).all()
    for m in messages[:-1]: # Exclude the user message we just added
        history.append({"role": m.role, "content": m.content})
        
    # Set conversation title dynamically if it is default
    if conv.title == "New Conversation":
        # First 4 words of the query
        conv.title = " ".join(query.split()[:4]) + "..."
        db.commit()

    async def event_generator():
        # Retrieve RAG answer
        # Since standard DB call is blocking, run in executive thread
        loop = asyncio.get_event_loop()
        response_text, citations = await loop.run_in_executor(
            None, RAGEngine.generate_response, db, collection, query, history
        )
        
        # Save assistant message
        assistant_msg = Message(
            conversation_id=conv_id,
            role="assistant",
            content=response_text,
            citations=citations
        )
        db.add(assistant_msg)
        db.commit()
        db.refresh(assistant_msg)
        
        # Yield the tokens chunk by chunk to simulate stream
        # Split by words/whitespace
        tokens = re.findall(r'\S+\s*', response_text)
        
        for token in tokens:
            data = {"type": "content", "delta": token}
            yield f"data: {json.dumps(data)}\n\n"
            # Add micro-delay for smooth experience
            await asyncio.sleep(0.01)
            
        # Send citations and DB IDs so frontend can display clickable sources and submit feedback
        data = {
            "type": "citations",
            "message_id": assistant_msg.id,
            "citations": citations
        }
        yield f"data: {json.dumps(data)}\n\n"
        
        # Send done packet
        yield "data: {\"type\": \"done\"}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
