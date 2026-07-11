import re
from typing import List, Dict, Any, Tuple
from loguru import logger
from sqlalchemy.orm import Session
from app.core.config import settings
from app.models.models import Chunk, Document
from app.services.vector_db import VectorDBService

# Import SDKs with fallback
try:
    import google.generativeai as genai
except ImportError:
    genai = None

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

try:
    import anthropic
except ImportError:
    anthropic = None

class RAGEngine:
    @staticmethod
    def hybrid_search(db: Session, collection_name: str, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Retrieves relevant document chunks using hybrid search:
        1. Dense vector search in Qdrant.
        2. Database keyword search (SQL ILIKE).
        Combines results using Reciprocal Rank Fusion (RRF).
        """
        logger.info(f"Executing hybrid search in collection '{collection_name}' for query: '{query}'")
        
        # 1. Semantic Search
        semantic_results = VectorDBService.search_similarity(collection_name, query, limit=limit * 2)
        
        # 2. Database Keyword Search
        keyword_results = RAGEngine._db_keyword_search(db, collection_name, query, limit=limit * 2)
        
        # 3. Reciprocal Rank Fusion (RRF)
        # RRF formula: RRF_score = sum(1 / (k + rank)) where k = 60
        rrf_scores: Dict[Tuple[int, int], Dict[str, Any]] = {} # keyed by (document_id, chunk_index)
        k = 60
        
        # Score semantic results
        for rank, hit in enumerate(semantic_results):
            doc_id = hit["document_id"]
            # Find chunk index by checking database
            chunk_obj = db.query(Chunk).filter(Chunk.document_id == doc_id, Chunk.text == hit["text"]).first()
            chunk_idx = chunk_obj.chunk_index if chunk_obj else 0
            
            key = (doc_id, chunk_idx)
            if key not in rrf_scores:
                rrf_scores[key] = {
                    "chunk": hit,
                    "score": 0.0
                }
            rrf_scores[key]["score"] += 1.0 / (k + rank + 1)
            
        # Score keyword results
        for rank, chunk in enumerate(keyword_results):
            key = (chunk.document_id, chunk.chunk_index)
            if key not in rrf_scores:
                # Find document filename
                doc = db.query(Document).filter(Document.id == chunk.document_id).first()
                filename = doc.filename if doc else "Unknown"
                
                rrf_scores[key] = {
                    "chunk": {
                        "text": chunk.text,
                        "document_id": chunk.document_id,
                        "filename": filename,
                        "page_number": chunk.page_number or 1,
                        "section_header": chunk.section_header or "",
                        "collection_name": collection_name
                    },
                    "score": 0.0
                }
            rrf_scores[key]["score"] += 1.0 / (k + rank + 1)
            
        # Sort and limit
        sorted_hits = sorted(rrf_scores.values(), key=lambda x: x["score"], reverse=True)
        final_results = [hit["chunk"] for hit in sorted_hits[:limit]]
        
        logger.info(f"Hybrid search returned {len(final_results)} fused results")
        return final_results

    @staticmethod
    def _db_keyword_search(db: Session, collection_name: str, query: str, limit: int = 10) -> List[Chunk]:
        # Simple extraction of keywords from query
        words = re.findall(r'\b\w{3,15}\b', query.lower())
        if not words:
            return []
            
        # Select chunks belonging to documents in the collection
        query_filter = db.query(Chunk).join(Document)
        query_filter = query_filter.filter(Document.collection_name == collection_name)
        
        # Build keyword search using ILIKE
        conditions = []
        for word in words[:5]: # limit keywords to top 5 to avoid slow queries
            conditions.append(Chunk.text.ilike(f"%{word}%"))
            
        if not conditions:
            return []
            
        from sqlalchemy import or_
        query_filter = query_filter.filter(or_(*conditions))
        return query_filter.limit(limit).all()

    @staticmethod
    def generate_response(db: Session, collection_name: str, query: str, conversation_history: List[Dict[str, str]] = None) -> Tuple[str, List[Dict[str, Any]]]:
        """
        Performs hybrid search, builds RAG context, prompts the LLM, and formats response citations.
        """
        # Retrieve context chunks
        chunks = RAGEngine.hybrid_search(db, collection_name, query, limit=5)
        
        if not chunks:
            return "The requested information is not available in the current SAP knowledge base.", []
            
        # Create prompt
        context_str = ""
        for i, chunk in enumerate(chunks):
            context_str += f"--- CONTEXT BLOCK {i+1} ---\n"
            context_str += f"Source Document: {chunk['filename']}\n"
            context_str += f"Page Number: {chunk['page_number']}\n"
            context_str += f"Section Header: {chunk['section_header']}\n"
            context_str += f"Content:\n{chunk['text']}\n\n"
            
        history_str = ""
        if conversation_history:
            for turn in conversation_history[-6:]: # Include last 3 turns
                history_str += f"{turn['role'].upper()}: {turn['content']}\n"

        prompt = f"""You are an expert SAP Knowledge AI Assistant. You must answer the user's question ONLY using the provided context blocks.

KNOWLEDGE BOUNDARY RULES:
- If the requested information is not explicitly found in the Context Blocks below, respond exactly with: "The requested information is not available in the current SAP knowledge base."
- Do not fabricate SAP transaction codes (T-Codes), config steps, or code guidelines.
- Never state that you have access to other databases or files unless they are given in the context.

CITATIONS RULES:
- For every statement or claim you make, append a bracketed index of the Context Block that supports it (e.g. [1], [2], or [1][3]).
- Do not cite blocks that do not support the sentence.
- Example: "To create an ALV report, use the reuse_alv_grid_display function [1]. You must define a fieldcatalog [2]."

FORMATTING RULES:
- Print code snippets in standard Markdown code blocks. For ABAP code, use ```abap. For SQL, use ```sql.
- Organize complex steps using bold headers, bullet lists, or tables.

--- CONTEXT BLOCKS ---
{context_str}

--- CONVERSATION HISTORY ---
{history_str}

USER QUESTION: {query}
ASSISTANT RESPONSE:"""

        # Generate response using LLM
        response_text = ""
        
        # 1. Try Gemini
        if settings.GEMINI_API_KEY:
            if genai:
                try:
                    genai.configure(api_key=settings.GEMINI_API_KEY)
                    model = genai.GenerativeModel('gemini-1.5-flash')
                    response = model.generate_content(prompt)
                    response_text = response.text
                except Exception as e:
                    logger.error(f"Gemini generation failed: {str(e)}")
            else:
                logger.warning("google-generativeai module not imported.")
                
        # 2. Try OpenAI fallback
        if not response_text and settings.OPENAI_API_KEY:
            if OpenAI:
                try:
                    client = OpenAI(api_key=settings.OPENAI_API_KEY)
                    response = client.chat.completions.create(
                        model="gpt-4o-mini",
                        messages=[{"role": "user", "content": prompt}],
                        temperature=0.0
                    )
                    response_text = response.choices[0].message.content
                except Exception as e:
                    logger.error(f"OpenAI generation failed: {str(e)}")
                    
        # 3. Try Anthropic fallback
        if not response_text and settings.ANTHROPIC_API_KEY:
            if anthropic:
                try:
                    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
                    message = client.messages.create(
                        model="claude-3-5-sonnet-20240620",
                        max_tokens=2000,
                        temperature=0.0,
                        messages=[{"role": "user", "content": prompt}]
                    )
                    response_text = message.content[0].text
                except Exception as e:
                    logger.error(f"Anthropic generation failed: {str(e)}")

        # 4. Mock Fallback (for testing / development without active keys)
        if not response_text:
            logger.warning("No API keys found. Generating local mocked RAG response.")
            # Simple keyword matching mockup to display retrieved text
            snippet = chunks[0]["text"][:300] + "..."
            response_text = f"Here is the information about your query found in the SAP knowledge documents:\n\n* **Topic Details**: {snippet} [1]\n\n*Please configure an LLM API key (e.g. GEMINI_API_KEY) in backend/.env to get real generative responses.*"

        # Check knowledge boundary violation in response
        if "information is not available" in response_text.lower() or "not available in the current sap knowledge" in response_text.lower():
            return "The requested information is not available in the current SAP knowledge base.", []

        # Parse citations
        citations = []
        # Find all brackets like [1], [2], [1][2], etc.
        citation_indices = set(map(int, re.findall(r'\[(\d+)\]', response_text)))
        
        for idx in citation_indices:
            if 0 < idx <= len(chunks):
                chunk = chunks[idx - 1]
                citations.append({
                    "doc_name": chunk["filename"],
                    "page": chunk["page_number"],
                    "section": chunk["section_header"],
                    "url": None # can add external document links later
                })
                
        return response_text, citations
