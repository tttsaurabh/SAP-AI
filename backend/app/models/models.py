import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text, JSON
from sqlalchemy import Enum as SQLAlchemyEnum
from sqlalchemy.orm import relationship
from app.core.database import Base
from app.core.roles import Role, DocumentStatus, MessageRole

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    full_name = Column(String, nullable=True)
    role = Column(
        SQLAlchemyEnum(Role, name="role_enum", values_callable=lambda e: [m.value for m in e]),
        default=Role.END_USER,
    )  # Super Admin, SAP Knowledge Manager, SAP Consultant, End User, Guest
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    conversations = relationship("Conversation", back_populates="user", cascade="all, delete-orphan")

class Collection(Base):
    __tablename__ = "collections"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True, nullable=False)
    created_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    # Stamped at first-ingest time (get-or-create on first document upload into
    # this collection) with settings.EMBEDDING_MODEL, so later uploads into the
    # same collection can be checked for embedding-space mismatches instead of
    # silently mixing vectors from different models in one vector index.
    embedding_model = Column(String, nullable=True)
    embedding_version = Column(String, nullable=True)

    documents = relationship("Document", back_populates="collection")

class Document(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String, index=True, nullable=False)
    file_path = Column(String, nullable=False)
    file_size = Column(Integer, default=0)
    # NOTE (Phase 1 schema hardening): `collection_name` is kept alongside the
    # new `collection_id` FK below as a denormalized display cache, to avoid a
    # bigger breaking change to the upload/list/search API surface in this
    # phase. `collection_id` is the source of truth for the Collection
    # relationship (including embedding_model bookkeeping); `collection_name`
    # should be treated as read-only/derived and is a candidate for removal
    # once the frontend and vector-store code are fully migrated to
    # collection_id. See CLAUDE.md Work Log for the Phase 1 entry.
    collection_name = Column(String, default="Default", index=True)
    collection_id = Column(Integer, ForeignKey("collections.id", ondelete="SET NULL"), nullable=True)
    document_type = Column(String, nullable=True) # PDF, docx, CSV, Excel, TXT, etc.
    status = Column(
        SQLAlchemyEnum(DocumentStatus, name="document_status_enum", values_callable=lambda e: [m.value for m in e]),
        default=DocumentStatus.PROCESSING,
    )  # processing, active, failed
    total_chunks = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    chunks = relationship("Chunk", back_populates="document", cascade="all, delete-orphan")
    collection = relationship("Collection", back_populates="documents")

class Chunk(Base):
    __tablename__ = "chunks"

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    text = Column(Text, nullable=False)
    chunk_index = Column(Integer, nullable=False)
    page_number = Column(Integer, nullable=True)
    section_header = Column(String, nullable=True)
    chunk_metadata = Column(JSON, default=dict) # To store custom details like tags, bounding boxes, tables, etc.
    # Vector ID used in the vector store (Pinecone/Qdrant), generated once in
    # documents.py's upload flow and reused for both the vector upsert call
    # and this column, so id-generation logic lives in exactly one place.
    vector_id = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    document = relationship("Document", back_populates="chunks")

class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String, default="New Conversation")
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    user = relationship("User", back_populates="conversations")
    messages = relationship("Message", back_populates="conversation", cascade="all, delete-orphan")

class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True)
    role = Column(
        SQLAlchemyEnum(MessageRole, name="message_role_enum", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
    )  # user or assistant
    content = Column(Text, nullable=False)
    citations = Column(JSON, default=list) # List of dicts representing sources: [{"doc_name": "...", "page": 5, "section": "...", "url": "..."}]
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    conversation = relationship("Conversation", back_populates="messages")
    feedbacks = relationship("Feedback", back_populates="message", cascade="all, delete-orphan")

class Feedback(Base):
    __tablename__ = "feedbacks"

    id = Column(Integer, primary_key=True, index=True)
    message_id = Column(Integer, ForeignKey("messages.id", ondelete="CASCADE"), nullable=False, index=True)
    score = Column(Integer, nullable=False) # 1 = Thumbs Up, -1 = Thumbs Down
    comments = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    message = relationship("Message", back_populates="feedbacks")
