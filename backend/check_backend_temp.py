from app.core.config import settings

print('Backend Environment Check')
print('=' * 70)
print('DATABASE_URL: ' + (settings.DATABASE_URL[:50] + '...' if settings.DATABASE_URL else 'NOT SET'))
print('SUPABASE_DB_URL: ' + (settings.SUPABASE_DB_URL[:50] + '...' if settings.SUPABASE_DB_URL else 'NOT SET'))
print('EMBEDDING_MODEL: ' + settings.EMBEDDING_MODEL)
print('EMBEDDING_DIMENSION: ' + str(settings.EMBEDDING_DIMENSION))
print()

try:
    from app.core.database import SessionLocal
    db = SessionLocal()
    from app.models.models import Document
    count = db.query(Document).count()
    db.close()
    print('[OK] Local DB connection works (' + str(count) + ' documents)')
except Exception as e:
    print('[FAIL] DB connection error: ' + str(e)[:150])
