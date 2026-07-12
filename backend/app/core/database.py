from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from app.core.config import settings

# For sqlite fallback during testing/dev if postgres is not ready
db_url = settings.DATABASE_URL
if db_url.startswith("postgresql"):
    # SQLAlchemy requires postgresql:// instead of postgres://
    db_url = db_url.replace("postgres://", "postgresql://", 1)

# Check if sqlite is configured (e.g. sqlite:///./test.db)
connect_args = {}
pool_kwargs = {}
if db_url.startswith("sqlite"):
    connect_args = {"check_same_thread": False}
else:
    # pool_pre_ping avoids handing out a connection the DB (or an
    # intervening proxy/load balancer) has silently closed after sitting
    # idle -- without it, that shows up as an intermittent failed/slow
    # query instead of a clean reconnect. pool_recycle keeps connections
    # from living long enough to hit that in the first place. Matters most
    # when DATABASE_URL points at a remote Postgres reached over the
    # public internet (see backend/PERFORMANCE_AUDIT.md).
    pool_kwargs = {
        "pool_pre_ping": True,
        "pool_recycle": 1800,
        "pool_size": 10,
        "max_overflow": 20,
    }

engine = create_engine(db_url, connect_args=connect_args, **pool_kwargs)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
