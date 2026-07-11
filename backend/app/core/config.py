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
    
    # DB Connections
    DATABASE_URL: str = "postgresql://sapadmin:sappassword@localhost:5432/sap_knowledge_db"
    QDRANT_HOST: str = "localhost"
    QDRANT_PORT: int = 6333
    REDIS_URL: str = "redis://localhost:6379/0"
    
    # LLMs API Keys
    GEMINI_API_KEY: str = ""
    OPENAI_API_KEY: str = ""
    ANTHROPIC_API_KEY: str = ""
    
    # Ingestion Configurations
    UPLOADS_DIR: str = "./uploads"
    OCR_ENABLED: bool = False
    EMBEDDING_MODEL: str = "local:sentence-transformers/all-MiniLM-L6-v2"
    RERANK_ENABLED: bool = False
    RERANK_MODEL: str = ""
    
    # Vector DB Backend
    VECTOR_DB_BACKEND: str = "pinecone"  # "pinecone" or "qdrant"
    PINECONE_API_KEY: str = ""
    PINECONE_INDEX_NAME: str = "sap-knowledge"
    
    # PDF Parser Engine
    PDF_PARSER_ENGINE: str = "pymupdf"  # "pymupdf" or "unlimited_ocr"
    
    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()

# Ensure uploads folder exists
os.makedirs(settings.UPLOADS_DIR, exist_ok=True)
