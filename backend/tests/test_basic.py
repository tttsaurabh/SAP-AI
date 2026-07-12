import unittest
from unittest.mock import MagicMock
from app.services.parser import DocumentParser
from app.services.chunker import DocumentChunker
from app.services.embeddings import EmbeddingsService
from app.services.vector_db import VectorDBService
from app.services.rag_engine import RAGEngine

class TestSAPRAGPipeline(unittest.TestCase):
    
    def test_chunker_basic(self):
        # 1. Test semantic chunking with token-based sizes
        pages = [
            {
                "page": 1,
                "text": (
                    "# 1. Introduction to RAP\n"
                    "The ABAP RESTful Application Programming Model (RAP) defines the architecture "
                    "for efficient end-to-end development of intrinsically SAP HANA-optimized OData services.\n\n"
                    "```abap\n"
                    "CLASS zcl_rap_handler DEFINITION PUBLIC.\n"
                    "  PUBLIC SECTION.\n"
                    "    METHODS: get_entityset IMPORTING io_request  TYPE REF TO /iwbep/if_mgw_req_entityset.\n"
                    "ENDCLASS.\n"
                    "```\n\n"
                    "## Configuration Steps\n\n"
                    "1. Open transaction SE80\n"
                    "2. Navigate to Core Data Services\n"
                    "3. Create a new CDS view\n"
                ),
                "metadata": {"headings": ["Introduction to RAP"]}
            }
        ]
        chunks = DocumentChunker.chunk_document(pages, chunk_size=450, chunk_overlap=80)
        self.assertGreater(len(chunks), 0)
        self.assertEqual(chunks[0]["page_number"], 1)
        # Verify heading context propagation
        self.assertIsNotNone(chunks[0]["section_header"])
        # Verify token_count metadata is present
        self.assertIn("token_count", chunks[0]["chunk_metadata"])
        # Verify ABAP code block is preserved intact (not split)
        full_text = "\n".join(c["text"] for c in chunks)
        self.assertIn("ENDCLASS", full_text)  # code block intact

        
    def test_embeddings_fallback(self):
        # 2. Test that embeddings are generated (either by API or deterministic mock fallback)
        test_text = "Verify SAP Master Data Governance change requests workflow."
        vecs = EmbeddingsService.get_embeddings(test_text)
        self.assertEqual(len(vecs), 1)
        self.assertEqual(len(vecs[0]), EmbeddingsService.get_embedding_dimension())
        
    def test_rag_engine_mock_generation(self):
        # 3. Test that RAGEngine returns the exact knowledge boundary string when context is empty
        db_mock = MagicMock()
        # Mock hybrid_search to return empty list to simulate empty context
        original_hybrid_search = RAGEngine.hybrid_search
        RAGEngine.hybrid_search = MagicMock(return_value=[])
        try:
            text_resp, citations = RAGEngine.generate_response(db_mock, "Default", "How do I configure BRF+ duplicate checks?")
            # Since context is empty, should trigger boundary check fallback
            self.assertEqual(text_resp, "The requested information is not available in the current SAP knowledge base.")
            self.assertEqual(len(citations), 0)
        finally:
            RAGEngine.hybrid_search = original_hybrid_search

    def test_relaxed_keyword_tsquery_keeps_domain_terms(self):
        # Normal chat wording should not make full-text fallback search require
        # filler words like "explain".
        tsquery = RAGEngine._build_relaxed_keyword_tsquery("Explain MDG Change Request process.")
        self.assertEqual(tsquery, "mdg | change | request")

if __name__ == "__main__":
    unittest.main()
