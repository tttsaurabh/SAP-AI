import os
import sys
from sqlalchemy.orm import Session

# Setup python path to import app correctly
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.core.database import SessionLocal, Base, engine
from app.models.models import Document, Chunk
from app.services.parser import DocumentParser
from app.services.chunker import DocumentChunker
from app.services.vector_db import get_vector_backend

def seed_specification():
    target_dir = "./uploads"
    target_filename = "sap_governance_spec.txt"
    target_file_path = os.path.join(target_dir, target_filename)
    collection_name = "Default"

    # Ensure uploads directory exists
    os.makedirs(target_dir, exist_ok=True)

    if not os.path.exists(target_file_path):
        print(f"Target specification file not found at {target_file_path}")
        return

    # 2. Database Session setup
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        # Check if already seeded to avoid duplicates
        existing_doc = db.query(Document).filter(Document.filename == target_filename).first()
        if existing_doc:
            print(f"Document {target_filename} already exists. Deleting to re-ingest...")
            # Delete vectors
            get_vector_backend().delete_document_vectors(existing_doc.collection_name, existing_doc.id)
            # Delete DB record (cascade deletes chunks)
            db.delete(existing_doc)
            db.commit()

        file_size = os.path.getsize(target_file_path)

        # 3. Create Document in DB
        db_doc = Document(
            filename=target_filename,
            file_path=target_file_path,
            file_size=file_size,
            collection_name=collection_name,
            document_type="TXT",
            status="processing",
            total_chunks=0
        )
        db.add(db_doc)
        db.commit()
        db.refresh(db_doc)

        print(f"Created Document record in DB with ID: {db_doc.id}")

        # 4. Parse file
        pages = DocumentParser.parse_file(target_file_path, target_filename)

        # 5. Chunk file (pass defaults explicitly so they can be persisted below)
        chunk_size = DocumentChunker.DEFAULT_CHUNK_SIZE_TOKENS
        chunk_overlap = DocumentChunker.DEFAULT_CHUNK_OVERLAP_TOKENS
        chunks = DocumentChunker.chunk_document(pages, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
        db_doc.chunk_size = chunk_size
        db_doc.chunk_overlap = chunk_overlap

        # 6. Save chunks in DB
        db_chunks = []
        for c in chunks:
            chunk_obj = Chunk(
                document_id=db_doc.id,
                text=c["text"],
                chunk_index=c["chunk_index"],
                page_number=c["page_number"],
                section_header=c["section_header"],
                chunk_metadata=c["chunk_metadata"]
            )
            db.add(chunk_obj)
            db_chunks.append(chunk_obj)
        db.commit()

        print(f"Saved {len(db_chunks)} chunks to PostgreSQL database.")

        # 7. Index chunks in vector DB
        get_vector_backend().upsert_chunks(
            collection_name=collection_name,
            document_id=db_doc.id,
            filename=target_filename,
            chunks=chunks
        )

        # 8. Mark document as active
        db_doc.status = "active"
        db_doc.total_chunks = len(chunks)
        db.commit()

        print(f"Document ingestion completed successfully for {target_filename}!")
    except Exception as e:
        print(f"Failed to seed document: {str(e)}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    seed_specification()
