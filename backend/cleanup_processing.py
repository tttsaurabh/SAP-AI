from app.core.database import SessionLocal
from app.models.models import Document, Chunk

db = SessionLocal()

# Get documents in PROCESSING status
processing_docs = db.query(Document).filter(Document.status == 'processing').all()

print(f"Deleting {len(processing_docs)} PROCESSING documents...\n")

for doc in processing_docs:
    print(f"  - {doc.filename}")
    db.delete(doc)

db.commit()

# Show final state
active_docs = db.query(Document).filter(Document.status == 'active').all()
total_chunks = db.query(Chunk).count()

print(f"\nCleanup complete!")
print(f"Active documents: {len(active_docs)}")
print(f"Total chunks: {total_chunks}")

for doc in active_docs:
    chunks_for_doc = db.query(Chunk).filter(Chunk.document_id == doc.id).count()
    print(f"  - {doc.filename}: {chunks_for_doc} chunks")

db.close()
