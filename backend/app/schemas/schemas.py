from pydantic import BaseModel, EmailStr, Field
from typing import List, Optional, Dict, Any
from datetime import datetime

# --- Token & Auth Schemas ---
class Token(BaseModel):
    access_token: str
    token_type: str
    role: str
    email: str
    full_name: Optional[str] = None

class TokenData(BaseModel):
    email: Optional[str] = None
    role: Optional[str] = None

class UserBase(BaseModel):
    email: EmailStr
    full_name: Optional[str] = None

class UserCreate(UserBase):
    password: str
    role: Optional[str] = "End User" # Super Admin, SAP Knowledge Manager, SAP Consultant, End User, Guest

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class UserResponse(UserBase):
    id: int
    role: str
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True

# --- Document & Chunk Schemas ---
class DocumentResponse(BaseModel):
    id: int
    filename: str
    file_path: str
    file_size: int
    collection_name: str
    collection_id: Optional[int] = None
    document_type: Optional[str]
    status: str
    # Populated when background ingestion fails (see
    # process_document_ingestion in api/documents.py); None while
    # processing/active or for documents ingested before this field existed.
    error_message: Optional[str] = None
    total_chunks: int
    created_at: datetime

    class Config:
        from_attributes = True

class ChunkResponse(BaseModel):
    id: int
    document_id: int
    text: str
    chunk_index: int
    page_number: Optional[int]
    section_header: Optional[str]
    chunk_metadata: Dict[str, Any]

    class Config:
        from_attributes = True

# --- Collection Schemas ---
class CollectionResponse(BaseModel):
    id: int
    name: str
    created_by: Optional[int] = None
    created_at: datetime
    embedding_model: Optional[str] = None
    embedding_version: Optional[str] = None

    class Config:
        from_attributes = True

# --- Chat & Citation Schemas ---
class CitationSchema(BaseModel):
    doc_name: str
    page: Optional[int] = None
    section: Optional[str] = None
    url: Optional[str] = None
    chunk_id: Optional[int] = None
    # Actual cited passage text from the source chunk (possibly truncated --
    # see RAGEngine.generate_response). Defaults to "" for citations saved
    # before this field existed, so older messages deserialize cleanly; the
    # frontend renders an explicit "unavailable" fallback rather than fake
    # placeholder text when this is empty.
    text: str = ""

class MessageCreate(BaseModel):
    content: str

class MessageResponse(BaseModel):
    id: int
    conversation_id: int
    role: str
    content: str
    citations: List[CitationSchema] = []
    created_at: datetime

    class Config:
        from_attributes = True

# --- "Explain simply" chat-widget feature ---
class ExplainSimplyRequest(BaseModel):
    # References an existing Chunk row so the explanation is always grounded
    # in real, server-resolved retrieved content -- never arbitrary
    # client-supplied "context" text.
    chunk_id: int
    query: str

class ExplainSimplyResponse(BaseModel):
    explanation: str

class ConversationCreate(BaseModel):
    title: Optional[str] = "New Conversation"

class ConversationResponse(BaseModel):
    id: int
    user_id: int
    title: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class ConversationDetail(ConversationResponse):
    messages: List[MessageResponse] = []

    class Config:
        from_attributes = True

# --- Feedback Schemas ---
class FeedbackCreate(BaseModel):
    message_id: int
    score: int = Field(..., ge=-1, le=1) # -1 or 1
    comments: Optional[str] = None

class FeedbackResponse(BaseModel):
    id: int
    message_id: int
    score: int
    comments: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True

# --- Analytics Schemas ---
class DocumentAnalytics(BaseModel):
    total_documents: int
    total_chunks: int
    total_size_bytes: int
    status_counts: Dict[str, int]
    collection_counts: Dict[str, int]

class ConversationAnalytics(BaseModel):
    total_conversations: int
    total_messages: int
    total_feedbacks: int
    positive_feedbacks: int
    negative_feedbacks: int
