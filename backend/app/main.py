import os
import time
from contextlib import asynccontextmanager

from alembic import command
from alembic.config import Config as AlembicConfig
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.concurrency import run_in_threadpool
from loguru import logger

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.security import get_password_hash
from app.core.roles import Role
from app.models.models import User
from app.services.embeddings import EmbeddingsService
from app.api import auth, documents, chat, admin, sap_agentic

# Path to backend/alembic.ini, regardless of the process's current working directory.
ALEMBIC_INI_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "alembic.ini")

# Run pending Alembic migrations up to head. This is the single source of
# schema truth going forward -- schema changes should be made via new
# Alembic revisions, not by editing models.py alone.
try:
    logger.info("Running Alembic migrations to head...")
    alembic_cfg = AlembicConfig(os.path.normpath(ALEMBIC_INI_PATH))
    command.upgrade(alembic_cfg, "head")
    logger.info("Alembic migrations applied successfully.")
    
    # Insert default super-admin user for immediate usability
    db = SessionLocal()
    try:
        admin_user = db.query(User).filter(User.email == "admin").first()
        if not admin_user:
            logger.info("Creating default administrator account: admin")
            default_admin = User(
                email="admin",
                hashed_password=get_password_hash("admin"),
                full_name="SAP Admin Manager",
                role=Role.SUPER_ADMIN,
                is_active=True
            )
            db.add(default_admin)
            
            # Create a test end-user account as well
            default_user = User(
                email="admin2",
                hashed_password=get_password_hash("admin"),
                full_name="SAP Consultant User",
                role=Role.CONSULTANT,
                is_active=True
            )
            db.add(default_user)
            db.commit()
            logger.info("Default administrator and consultant profiles created.")
    except Exception as e:
        logger.error(f"Failed to seed default database users: {str(e)}")
    finally:
        db.close()
        
except Exception as e:
    logger.exception(f"Database schema initialization failed: {str(e)}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Warm the local embedding model at process startup instead of paying
    # its multi-second load cost inline on the first user's chat request
    # (see backend/PERFORMANCE_AUDIT.md). run_in_threadpool so this doesn't
    # block anything else during startup any more than necessary.
    await run_in_threadpool(EmbeddingsService.warm_up)
    yield

# Create FastAPI Instance
app = FastAPI(
    title=settings.APP_NAME,
    description="Enterprise RAG Assistant trained on custom SAP knowledge documentation.",
    version="1.0.0",
    lifespan=lifespan,
)

# Set CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3001",
        "http://192.168.1.6:3000",
        "http://192.168.1.7:3001",
        "https://mdgbuddy.vercel.app",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def log_request_timing(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    duration_ms = (time.perf_counter() - start) * 1000
    logger.info(
        f"[timing] request duration_ms={duration_ms:.1f} "
        f"method={request.method} path={request.url.path} status={response.status_code}"
    )
    return response

# Register routes
app.include_router(auth.router)
app.include_router(documents.router)
app.include_router(chat.router)
app.include_router(admin.router)
app.include_router(sap_agentic.router)

@app.get("/")
def home():
    return {
        "status": "online",
        "app_name": settings.APP_NAME,
        "docs_url": "/docs"
    }
