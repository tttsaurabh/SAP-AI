import os
import gc

# ── Render Free Tier Memory Optimization (512MB RAM Limit) ───────────────────
# Limit PyTorch CPU threads and memory allocations to prevent OOM crashes.
# This saves ~100MB of RAM during startup and RAG execution.
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["VECLIB_MAXIMUM_THREADS"] = "1"
os.environ["NUMEXPR_NUM_THREADS"] = "1"
os.environ["TORCH_NUM_THREADS"] = "1"
os.environ["PYTORCH_MALLOC_CONF"] = "max_split_size_mb:32"

try:
    import torch
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    torch.set_grad_enabled(False)
except ImportError:
    pass

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
    # its multi-second load cost inline on the first user's chat request.
    # On Render this is opt-in because smaller instances may prefer faster
    # port binding over first-query latency.
    if settings.CHAT_PREWARM_ENABLED or not os.environ.get("RENDER"):
        await run_in_threadpool(EmbeddingsService.warm_up)
    else:
        logger.info("Render environment detected: skipping startup embedding model warm-up. Set CHAT_PREWARM_ENABLED=true to opt in.")
    gc.collect()  # Force garbage collection to release loading overhead RAM
    yield

# Create FastAPI Instance
app = FastAPI(
    title=settings.APP_NAME,
    description="Enterprise RAG Assistant trained on custom SAP knowledge documentation.",
    version="1.0.0",
    lifespan=lifespan,
)

# Parse CORS allowed origins from settings
origins = [origin.strip() for origin in settings.CORS_ALLOWED_ORIGINS.split(",") if origin.strip()]

# Set CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
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
