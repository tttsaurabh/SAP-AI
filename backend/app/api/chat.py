import json
import time
import asyncio
import threading
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from starlette.concurrency import run_in_threadpool
from sqlalchemy.orm import Session
from typing import List, Dict, Any, Optional
from loguru import logger

from app.core.database import get_db
from app.core.security import any_authenticated
from app.core.roles import Role, MessageRole
from app.core.timing import phase
from app.models.models import User, Conversation, Message, Feedback, Citation, Chunk
from app.schemas.schemas import ConversationResponse, ConversationDetail, MessageResponse, FeedbackCreate, FeedbackResponse, ExplainSimplyRequest, ExplainSimplyResponse
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
    if conv.user_id != current_user.id and current_user.role != Role.SUPER_ADMIN:
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
    if conv.user_id != current_user.id and current_user.role != Role.SUPER_ADMIN:
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

@router.post("/explain", response_model=ExplainSimplyResponse)
def explain_chunk_simply(
    payload: ExplainSimplyRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(any_authenticated)
):
    """
    "Explain this simply" chat-widget feature: re-fetches the chunk's
    canonical text server-side by id (rather than trusting client-supplied
    context text) and asks the LLM to explain it in plain language, per the
    hardened prompt in RAGEngine.explain_simply.
    """
    chunk = db.query(Chunk).filter(Chunk.id == payload.chunk_id).first()
    if not chunk:
        raise HTTPException(status_code=404, detail="Chunk not found")

    explanation = RAGEngine.explain_simply(payload.query, chunk.text)
    return ExplainSimplyResponse(explanation=explanation)

def _load_conversation(db: Session, conv_id: int) -> Optional[Conversation]:
    with phase("chat.conversation_lookup", conv_id=conv_id):
        return db.query(Conversation).filter(Conversation.id == conv_id).first()

def _save_user_message(db: Session, conv_id: int, query: str) -> Message:
    with phase("chat.save_user_message", conv_id=conv_id):
        user_msg = Message(conversation_id=conv_id, role=MessageRole.USER, content=query, citations=[])
        db.add(user_msg)
        db.commit()
        db.refresh(user_msg)
        return user_msg

def _load_history(db: Session, conv_id: int) -> List[Message]:
    with phase("chat.load_history", conv_id=conv_id):
        return db.query(Message).filter(Message.conversation_id == conv_id).order_by(Message.created_at.asc()).all()

def _maybe_set_title(db: Session, conv: Conversation, query: str) -> None:
    if conv.title == "New Conversation":
        with phase("chat.set_title", conv_id=conv.id):
            # First 4 words of the query
            conv.title = " ".join(query.split()[:4]) + "..."
            db.commit()

def _save_assistant_message(db: Session, conv_id: int, response_text: str, citations: List[Dict[str, Any]]) -> Message:
    with phase("chat.save_assistant_message", conv_id=conv_id):
        assistant_msg = Message(
            conversation_id=conv_id,
            role=MessageRole.ASSISTANT,
            content=response_text,
            citations=citations
        )
        db.add(assistant_msg)
        db.commit()
        db.refresh(assistant_msg)
        return assistant_msg

def _save_citations(db: Session, conv_id: int, message_id: int, citations: List[Dict[str, Any]]) -> None:
    # Also persist a durable, joinable Citation row per citation (e.g.
    # "which chunks get cited most"). Additive alongside the JSON
    # `citations` column above, which stays the fast denormalized read
    # path for the chat UI. `chunk_id` may be None if the citation's
    # source chunk couldn't be resolved back to a DB row.
    if not citations:
        return
    with phase("chat.save_citations", conv_id=conv_id, count=len(citations)):
        db.bulk_save_objects([
            Citation(
                message_id=message_id,
                chunk_id=citation.get("chunk_id"),
                rank=rank
            )
            for rank, citation in enumerate(citations)
        ])
        db.commit()

@router.get("/conversations/{conv_id}/stream")
async def stream_chat_response(
    conv_id: int,
    query: str,
    request: Request,
    collection: str = "Default",
    db: Session = Depends(get_db),
    current_user: User = Depends(any_authenticated)
):
    # Each of these does a blocking DB round trip; run_in_threadpool keeps
    # them off the event loop so one slow request can't stall every other
    # concurrent request being served by this process (see
    # backend/PERFORMANCE_AUDIT.md).
    conv = await run_in_threadpool(_load_conversation, db, conv_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    await run_in_threadpool(_save_user_message, db, conv_id, query)

    # Retrieve history
    history = []
    messages = await run_in_threadpool(_load_history, db, conv_id)
    for m in messages[:-1]: # Exclude the user message we just added
        history.append({"role": m.role, "content": m.content})

    # Set conversation title dynamically if it is default
    await run_in_threadpool(_maybe_set_title, db, conv, query)

    async def event_generator():
        # RAGEngine.stream_response is a *synchronous* generator (the
        # provider SDKs -- google-generativeai / openai / anthropic -- are
        # all sync streaming interfaces). Bridge it into the async SSE
        # response by running it in a background thread that pushes each
        # yielded delta into an asyncio.Queue; this coroutine pulls from
        # the queue and forwards SSE `content` events as they arrive,
        # without blocking the event loop.
        loop = asyncio.get_event_loop()
        queue: asyncio.Queue = asyncio.Queue()
        chunks_out: List[Dict[str, Any]] = []
        DONE = object()
        generation_start = time.perf_counter()
        first_token_at = None

        def producer():
            try:
                for delta in RAGEngine.stream_response(db, collection, query, history, chunks_out=chunks_out):
                    if isinstance(delta, dict) and delta.get("type") == "status":
                        loop.call_soon_threadsafe(queue.put_nowait, ("status", delta.get("message", "")))
                    else:
                        loop.call_soon_threadsafe(queue.put_nowait, ("content", delta))
            except Exception as e:
                logger.exception(f"Streaming generation failed for conversation {conv_id}")
                loop.call_soon_threadsafe(queue.put_nowait, ("error", str(e)))
            finally:
                loop.call_soon_threadsafe(queue.put_nowait, (DONE, None))

        thread = threading.Thread(target=producer, daemon=True)
        thread.start()

        full_text_parts: List[str] = []
        disconnected = False
        tokens_since_disconnect_check = 0

        while True:
            kind, payload = await queue.get()
            if kind == "content":
                if first_token_at is None:
                    first_token_at = time.perf_counter()
                    logger.info(
                        f"[timing] chat.time_to_first_token duration_ms="
                        f"{(first_token_at - generation_start) * 1000:.1f} conv_id={conv_id}"
                    )
                full_text_parts.append(payload)
                data = {"type": "content", "delta": payload}
                yield f"data: {json.dumps(data)}\n\n"

                # Best-effort disconnect handling: check every few tokens
                # rather than on every single one (is_disconnected() is
                # itself an async call). If the client is gone, stop
                # pulling/forwarding further tokens -- the background
                # thread's in-flight provider SDK call cannot always be
                # cancelled from here, but we stop consuming/forwarding at
                # minimum, and (below) skip the citation-save DB work for
                # an abandoned stream.
                tokens_since_disconnect_check += 1
                if tokens_since_disconnect_check >= 5:
                    tokens_since_disconnect_check = 0
                    if await request.is_disconnected():
                        disconnected = True
                        break
            elif kind == "error":
                logger.error(f"Chat stream error for conversation {conv_id}: {payload}")
                break
            elif kind == "status":
                data = {"type": "status", "message": payload}
                yield f"data: {json.dumps(data)}\n\n"
            elif kind is DONE:
                break

        logger.info(
            f"[timing] chat.total_generation duration_ms="
            f"{(time.perf_counter() - generation_start) * 1000:.1f} conv_id={conv_id}"
        )

        if disconnected:
            logger.info(f"Client disconnected mid-stream for conversation {conv_id}; skipping citation save.")
            return

        response_text = "".join(full_text_parts) or "An error occurred while generating the response."
        if not history:
            RAGEngine.set_cached_response(
                RAGEngine.response_cache_key(collection, query),
                response_text,
                chunks_out,
            )
        citations = RAGEngine.build_citations(response_text, chunks_out)

        assistant_msg = await run_in_threadpool(_save_assistant_message, db, conv_id, response_text, citations)
        await run_in_threadpool(_save_citations, db, conv_id, assistant_msg.id, citations)

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
