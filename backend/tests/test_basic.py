import unittest
from unittest.mock import MagicMock
from app.services.parser import DocumentParser
from app.services.chunker import DocumentChunker
from app.services.embeddings import EmbeddingsService
from app.services.vector_db import VectorDBService
from app.services.rag_engine import RAGEngine

class TestSAPRAGPipeline(unittest.TestCase):
    
    def test_chunker_basic(self):
        # 1. Test standard document chunking
        pages = [
            {
                "page": 1,
                "text": "SAP ABAP stands for Advanced Business Application Programming. It is a high-level programming language created by SAP. # 1. Introduction to RAP\nThe ABAP RESTful Application Programming Model (RAP) defines the architecture for efficient end-to-end development of intrinsically SAP HANA-optimized OData services.",
                "metadata": {"headings": ["ABAP Overview"]}
            }
        ]
        chunks = DocumentChunker.chunk_document(pages, chunk_size=200, chunk_overlap=20)
        self.assertGreater(len(chunks), 0)
        self.assertEqual(chunks[0]["page_number"], 1)
        # Verify heading context propagation
        self.assertIsNotNone(chunks[0]["section_header"])
        
    def test_embeddings_fallback(self):
        # 2. Test that embeddings are generated (either by API or deterministic mock fallback)
        test_text = "Verify SAP Master Data Governance change requests workflow."
        vecs = EmbeddingsService.get_embeddings(test_text)
        self.assertEqual(len(vecs), 1)
        self.assertEqual(len(vecs[0]), EmbeddingsService.get_embedding_dimension())
        
    def test_rag_engine_mock_generation(self):
        # 3. Test that RAGEngine returns the exact knowledge boundary string when context is empty
        db_mock = MagicMock()
        text_resp, citations = RAGEngine.generate_response(db_mock, "Default", "How do I configure BRF+ duplicate checks?")
        
        # Since DB is empty, should trigger boundary check fallback
        self.assertEqual(text_resp, "The requested information is not available in the current SAP knowledge base.")
        self.assertEqual(len(citations), 0)

if __name__ == "__main__":
    unittest.main()
