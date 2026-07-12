import os
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

# Load env file
load_dotenv()

class Settings(BaseSettings):
    APP_NAME: str = "SAP Knowledge AI Assistant"
    DEBUG: bool = True
    
    # Security
    JWT_SECRET: str = "sap-ai-assistant-dev-jwt-secret-key-123456"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 120
    CORS_ALLOWED_ORIGINS: str = "http://localhost:3000,http://127.0.0.1:3000,http://localhost:3001,http://127.0.0.1:3001,http://192.168.1.6:3000,http://192.168.1.7:3001,https://mdgbuddy.vercel.app,https://sapmdg.vercel.app"
    
    # ── Supabase Settings ────────────────────────────────────────────────────
    # Project URL from: Supabase → Settings → API
    SUPABASE_URL: str = ""
    # Anon/public key from: Supabase → Settings → API
    SUPABASE_ANON_KEY: str = ""
    # Service role key from: Supabase → Settings → API (keep secret!)
    SUPABASE_SERVICE_ROLE_KEY: str = ""
    # Full PostgreSQL connection string from: Supabase → Settings → Database
    SUPABASE_DB_URL: str = ""

    # ── SQLAlchemy DB URL ────────────────────────────────────────────────────
    # For Supabase: set to SUPABASE_DB_URL value
    # For local dev: set to sqlite:///./sap_knowledge.db
    DATABASE_URL: str = "sqlite:///./sap_knowledge.db"
    
    # LLMs API Keys
    GEMINI_API_KEY: str = ""
    OPENAI_API_KEY: str = ""
    ANTHROPIC_API_KEY: str = ""
    
    # LLM Models and Timeouts
    GEMINI_MODEL: str = "gemini-2.0-flash-lite"
    OPENAI_MODEL: str = "gpt-4o-mini"
    ANTHROPIC_MODEL: str = "claude-3-5-sonnet-latest"
    LLM_TIMEOUT_SECONDS: float = 25.0
    
    # Ingestion Configurations
    UPLOADS_DIR: str = "./uploads"
    OCR_ENABLED: bool = False
    EMBEDDING_MODEL: str = "gemini:text-embedding-004"
    RERANK_ENABLED: bool = False
    RERANK_MODEL: str = ""

    # ── Parent-child chunking (Phase 8b) ─────────────────────────────────────
    # Small "child" chunks are embedded/indexed for precise retrieval
    # matching; the larger "parent" chunk (SQL-only, never embedded) supplies
    # full surrounding context to the LLM once a child wins retrieval. Both
    # ingestion entry points (documents.py upload flow, ingest_public_pdfs.py)
    # read these so chunk granularity is no longer inconsistent between them
    # (previously 450 vs. 1200 tokens with no shared config -- see Phase 5
    # CLAUDE.md Work Log entry).
    PARENT_CHUNK_SIZE_TOKENS: int = 1000
    CHILD_CHUNK_SIZE_TOKENS: int = 300
    CHILD_CHUNK_OVERLAP_TOKENS: int = 60
    
    # ── Vector DB Backend ────────────────────────────────────────────────────
    # Options: "supabase" (pgvector — free), "pinecone", "qdrant"
    VECTOR_DB_BACKEND: str = "supabase"
    PINECONE_API_KEY: str = ""
    PINECONE_INDEX_NAME: str = "sap-knowledge"
    QDRANT_HOST: str = "localhost"
    QDRANT_PORT: int = 6333
    
    # Supabase pgvector table name
    SUPABASE_VECTOR_TABLE: str = "document_vectors"
    # Embedding dimension (384 for all-MiniLM-L6-v2, 1536 for OpenAI text-embedding-ada-002)
    EMBEDDING_DIMENSION: int = 384

    # PDF Parser Engine
    PDF_PARSER_ENGINE: str = "pymupdf"  # "pymupdf" or "unlimited_ocr"
    
    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()

# Ensure uploads folder exists
os.makedirs(settings.UPLOADS_DIR, exist_ok=True)
