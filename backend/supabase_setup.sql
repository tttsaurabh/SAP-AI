-- ============================================================
-- SAP AI Knowledge Assistant — Supabase Setup Script
-- Run this ONCE in: Supabase Dashboard → SQL Editor → New Query
-- ============================================================

-- Step 1: Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Step 2: Create the document_vectors table
-- Stores SAP document chunk embeddings for RAG similarity search
CREATE TABLE IF NOT EXISTS document_vectors (
    id              BIGSERIAL PRIMARY KEY,
    vector_id       TEXT UNIQUE NOT NULL,          -- canonical ID from app (e.g. doc1_chunk0)
    document_id     INTEGER NOT NULL,              -- references documents table in SQLite/PostgreSQL
    filename        TEXT NOT NULL,                 -- original PDF filename
    collection_name TEXT NOT NULL DEFAULT 'Default', -- domain grouping (e.g. 'Master Data', 'ABAP')
    chunk_text      TEXT NOT NULL,                 -- raw text of the chunk
    page_number     INTEGER DEFAULT 1,             -- source page in the document
    section_header  TEXT DEFAULT '',               -- extracted section heading
    embedding       VECTOR(384),                   -- 384-dim all-MiniLM-L6-v2 embedding
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Step 3: Create HNSW index for fast cosine similarity search
-- HNSW is significantly faster than IVFFlat for real-time RAG queries
CREATE INDEX IF NOT EXISTS document_vectors_embedding_idx
    ON document_vectors
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- Step 4: Create index for fast document-level queries
CREATE INDEX IF NOT EXISTS document_vectors_doc_idx
    ON document_vectors (document_id, collection_name);

-- Step 5: Create index for collection-level queries
CREATE INDEX IF NOT EXISTS document_vectors_collection_idx
    ON document_vectors (collection_name);

-- Step 6: Enable Row-Level Security (RLS) — recommended for Supabase
ALTER TABLE document_vectors ENABLE ROW LEVEL SECURITY;

-- Allow service_role full access (your FastAPI backend uses service_role key)
CREATE POLICY "service_role_all" ON document_vectors
    FOR ALL
    TO service_role
    USING (true)
    WITH CHECK (true);

-- Step 7: Create a helper function for similarity search (optional, for direct REST calls)
CREATE OR REPLACE FUNCTION search_document_vectors(
    query_embedding VECTOR(384),
    collection TEXT,
    match_count INT DEFAULT 5
)
RETURNS TABLE (
    vector_id       TEXT,
    document_id     INTEGER,
    filename        TEXT,
    collection_name TEXT,
    chunk_text      TEXT,
    page_number     INTEGER,
    section_header  TEXT,
    score           FLOAT
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT
        dv.vector_id,
        dv.document_id,
        dv.filename,
        dv.collection_name,
        dv.chunk_text,
        dv.page_number,
        dv.section_header,
        1 - (dv.embedding <=> query_embedding) AS score
    FROM document_vectors dv
    WHERE dv.collection_name = collection
    ORDER BY dv.embedding <=> query_embedding
    LIMIT match_count;
END;
$$;

-- ============================================================
-- Verification: Run these to confirm setup is correct
-- ============================================================

-- Check pgvector is enabled
SELECT * FROM pg_extension WHERE extname = 'vector';

-- Check table created
SELECT column_name, data_type 
FROM information_schema.columns 
WHERE table_name = 'document_vectors'
ORDER BY ordinal_position;

-- Check indexes created
SELECT indexname, indexdef 
FROM pg_indexes 
WHERE tablename = 'document_vectors';

-- ============================================================
-- NOTES:
-- - VECTOR(384) matches all-MiniLM-L6-v2 embedding model (384 dims)
-- - If you switch to OpenAI text-embedding-ada-002, change to VECTOR(1536)
-- - HNSW index (m=16, ef_construction=64) is optimal for <100K chunks
-- - For >100K chunks, increase ef_construction to 128
-- ============================================================
