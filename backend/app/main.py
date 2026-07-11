from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from app.core.config import settings
from app.core.database import engine, Base, SessionLocal
from app.core.security import get_password_hash
from app.models.models import User
from app.api import auth, documents, chat, admin, sap_agentic

# Setup SQL Database tables
try:
    logger.info("Initializing SQL Database schema...")
    Base.metadata.create_all(bind=engine)
    logger.info("SQL Schema initialized successfully.")
    
    # Insert default super-admin user for immediate usability
    db = SessionLocal()
    try:
        admin_user = db.query(User).filter(User.email == "admin@sap.com").first()
        if not admin_user:
            logger.info("Creating default administrator account: admin@sap.com")
            default_admin = User(
                email="admin@sap.com",
                hashed_password=get_password_hash("adminpassword"),
                full_name="SAP Admin Manager",
                role="Super Admin",
                is_active=True
            )
            db.add(default_admin)
            
            # Create a test end-user account as well
            default_user = User(
                email="consultant@sap.com",
                hashed_password=get_password_hash("consultantpassword"),
                full_name="SAP Consultant User",
                role="SAP Consultant",
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

# Create FastAPI Instance
app = FastAPI(
    title=settings.APP_NAME,
    description="Enterprise RAG Assistant trained on custom SAP knowledge documentation.",
    version="1.0.0",
)

# Set CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # In production, restrict this to Next.js host
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
