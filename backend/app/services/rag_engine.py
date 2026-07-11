import re
from typing import List, Dict, Any, Tuple
from loguru import logger
from sqlalchemy.orm import Session
from app.core.config import settings
from app.models.models import Chunk, Document
from app.services.vector_db import get_vector_backend

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
    def expand_query(query: str) -> str:
        """
        Expands typical SAP abbreviations to support hybrid keyword and semantic retrieval.
        """
        sap_abbreviations = {
            r"\bBP\b": "Business Partner",
            r"\bCR\b": "Change Request",
            r"\bMM\b": "Material Master",
            r"\bBAPI\b": "Business Application Programming Interface",
            r"\bMDG\b": "Master Data Governance",
            r"\bRAP\b": "RESTful Application Programming",
            r"\bCDS\b": "Core Data Services",
            r"\bFPM\b": "Floorplan Manager",
            r"\bBRF\+?\b": "Business Rules Framework plus",
            r"\bADT\b": "ABAP Development Tools",
            r"\bBADI\b": "Business Add-In",
            r"\bALV\b": "ABAP List Viewer",
            r"\bDDIC\b": "Data Dictionary",
        }
        expanded = query
        for pattern, expansion in sap_abbreviations.items():
            if re.search(pattern, query, re.IGNORECASE):
                if expansion.lower() not in query.lower():
                    expanded += f" {expansion}"
        return expanded

    @staticmethod
    def hybrid_search(db: Session, collection_name: str, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Retrieves relevant document chunks using hybrid search:
        1. Query expansion for SAP abbreviations.
        2. Dense vector search in Qdrant.
        3. Database keyword search (SQL ILIKE).
        4. Combines results using Reciprocal Rank Fusion (RRF).
        5. Context compression (deduplication).
        """
        # 1. Query Expansion
        expanded_query = RAGEngine.expand_query(query)
        logger.info(f"Executing hybrid search for query: '{query}' (Expanded: '{expanded_query}')")
        
        # 2. Semantic Search using expanded query (routed to Pinecone or Qdrant)
        vector_backend = get_vector_backend()
        semantic_results = vector_backend.search_similarity(collection_name, expanded_query, limit=limit * 3)
        
        # 3. Database Keyword Search using expanded query
        keyword_results = RAGEngine._db_keyword_search(db, collection_name, expanded_query, limit=limit * 3)
        
        # 4. Reciprocal Rank Fusion (RRF)
        # RRF formula: RRF_score = sum(1 / (k + rank)) where k = 60
        rrf_scores: Dict[Tuple[int, int], Dict[str, Any]] = {} # keyed by (document_id, chunk_index)
        k = 60
        
        # Score semantic results
        for rank, hit in enumerate(semantic_results):
            doc_id = hit["document_id"]
            # Find chunk row by checking database -- this reconciliation lookup
            # already existed to recover chunk_index; extend it to also
            # capture the real DB chunk_id, since the vector store payload
            # itself carries no chunk_id (only text/doc/page/section).
            chunk_obj = db.query(Chunk).filter(Chunk.document_id == doc_id, Chunk.text == hit["text"]).first()
            chunk_idx = chunk_obj.chunk_index if chunk_obj else 0
            hit["chunk_id"] = chunk_obj.id if chunk_obj else None

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
                        "chunk_id": chunk.id,
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
            
        # 5. Sort and Deduplicate / Compress
        sorted_hits = sorted(rrf_scores.values(), key=lambda x: x["score"], reverse=True)
        
        seen_texts = set()
        final_results = []
        for hit in sorted_hits:
            chunk = hit["chunk"]
            norm_text = re.sub(r'\s+', ' ', chunk["text"]).strip().lower()
            if len(norm_text) >= 20 and norm_text not in seen_texts:
                seen_texts.add(norm_text)
                final_results.append(chunk)
                if len(final_results) >= limit:
                    break
        
        logger.info(f"Hybrid search returned {len(final_results)} fused and compressed results")
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
    def _build_prompt(chunks: List[Dict[str, Any]], conversation_history: List[Dict[str, str]], query: str) -> str:
        """
        Builds the RAG prompt from retrieved context chunks + conversation
        history. Shared by both the non-streaming (`generate_response`) and
        streaming (`stream_response`) code paths so the prompt text itself
        never drifts between the two.
        """
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

        return f"""You are an expert SAP Knowledge AI Assistant. You must answer the user's question ONLY using the provided context blocks.

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

    @staticmethod
    def _mock_fallback_text(chunks: List[Dict[str, Any]]) -> str:
        """
        Canned local response used when no LLM API key is configured / every
        configured provider failed before producing any output. Not a true
        generative response -- just enough to display retrieved context and
        point the operator at the missing configuration.
        """
        logger.warning("No API keys found. Generating local mocked RAG response.")
        snippet = chunks[0]["text"][:300] + "..."
        return (
            f"Here is the information about your query found in the SAP knowledge documents:\n\n"
            f"* **Topic Details**: {snippet} [1]\n\n"
            f"*Please configure an LLM API key (e.g. GEMINI_API_KEY) in backend/.env to get real generative responses.*"
        )

    @staticmethod
    def build_citations(response_text: str, chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Parses `[N]`-bracket citation markers out of `response_text` and
        resolves them against the retrieved `chunks` list, returning the
        same citation dict shape persisted to `Message.citations` (JSON) and
        the `Citation` join table. Shared by both `generate_response` and
        `stream_response` so citation parsing/formatting never drifts
        between the non-streaming and streaming code paths.
        """
        citations = []
        # Find all brackets like [1], [2], [1][2], etc.
        citation_indices = set(map(int, re.findall(r'\[(\d+)\]', response_text)))

        for idx in sorted(citation_indices):
            if 0 < idx <= len(chunks):
                chunk = chunks[idx - 1]
                # Truncate to a generous ceiling above the chunker's default
                # target chunk size (450 tokens, ~1200-1800 chars typically)
                # so normal-sized chunks come through whole, while pathological
                # oversized chunks (e.g. an un-splittable code block) don't
                # blow up the citation payload.
                chunk_text = chunk.get("text", "") or ""
                citation_text = chunk_text[:1500]
                citations.append({
                    "doc_name": chunk["filename"],
                    "page": chunk["page_number"],
                    "section": chunk["section_header"],
                    "url": None, # can add external document links later
                    "chunk_id": chunk.get("chunk_id"),
                    "text": citation_text
                })

        return citations

    @staticmethod
    def generate_response(db: Session, collection_name: str, query: str, conversation_history: List[Dict[str, str]] = None) -> Tuple[str, List[Dict[str, Any]]]:
        """
        Performs hybrid search, builds RAG context, prompts the LLM, and formats response citations.

        Non-streaming path -- generates the *complete* response before
        returning. Kept around for callers that genuinely want a single
        blocking call (tests, scripts); the chat SSE endpoint uses
        `stream_response` instead (see Phase 3 CLAUDE.md entry).
        """
        # Retrieve context chunks
        chunks = RAGEngine.hybrid_search(db, collection_name, query, limit=5)

        if not chunks:
            return "The requested information is not available in the current SAP knowledge base.", []

        prompt = RAGEngine._build_prompt(chunks, conversation_history, query)

        # Generate response using LLM
        response_text = ""

        # 1. Try Gemini
        if settings.GEMINI_API_KEY:
            if genai:
                try:
                    genai.configure(api_key=settings.GEMINI_API_KEY)
                    model = genai.GenerativeModel('gemini-3.5-flash')
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
            response_text = RAGEngine._mock_fallback_text(chunks)

        # Check knowledge boundary violation in response
        if "information is not available" in response_text.lower() or "not available in the current sap knowledge" in response_text.lower():
            return "The requested information is not available in the current SAP knowledge base.", []

        citations = RAGEngine.build_citations(response_text, chunks)
        return response_text, citations

    # ------------------------------------------------------------------
    # Real streaming (Phase 3)
    # ------------------------------------------------------------------
    # Per-provider generators below each yield raw text deltas as the
    # underlying SDK produces them (`stream=True` on Gemini/OpenAI,
    # `messages.stream()` on Anthropic) -- no artificial buffering, no
    # re-chunking of an already-complete string.

    @staticmethod
    def _stream_gemini(prompt: str):
        genai.configure(api_key=settings.GEMINI_API_KEY)
        model = genai.GenerativeModel('gemini-3.5-flash')
        response = model.generate_content(prompt, stream=True)
        for chunk in response:
            # `.text` is a computed property that can raise (e.g. a chunk
            # with no parts, such as a safety-filtered piece) -- skip a bad
            # chunk instead of killing the whole stream over it.
            try:
                text = chunk.text
            except Exception:
                continue
            if text:
                yield text

    @staticmethod
    def _stream_openai(prompt: str):
        client = OpenAI(api_key=settings.OPENAI_API_KEY)
        stream = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            stream=True,
        )
        for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            content = getattr(delta, "content", None) if delta else None
            if content:
                yield content

    @staticmethod
    def _stream_anthropic(prompt: str):
        client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        with client.messages.stream(
            model="claude-3-5-sonnet-20240620",
            max_tokens=2000,
            temperature=0.0,
            messages=[{"role": "user", "content": prompt}],
        ) as stream:
            for text in stream.text_stream:
                yield text

    @staticmethod
    def _stream_llm_response(prompt: str, chunks: List[Dict[str, Any]]):
        """
        Tries providers in the same fallback order as `generate_response`
        (Gemini -> OpenAI -> Anthropic -> mock), but adapted for real
        streaming: once a provider has emitted at least one token to the
        caller, we can no longer cleanly discard it and switch providers
        mid-stream (the client has already seen those tokens over SSE), so
        a failure *after* first-token only propagates -- it does not
        silently fall back. A provider only gets skipped in favor of the
        next one if it raises (or produces nothing) before yielding
        anything.
        """
        providers = []
        if settings.GEMINI_API_KEY and genai:
            providers.append(("Gemini", RAGEngine._stream_gemini))
        else:
            logger.warning("Gemini not configured for streaming (missing API key or module).")
        if settings.OPENAI_API_KEY and OpenAI:
            providers.append(("OpenAI", RAGEngine._stream_openai))
        if settings.ANTHROPIC_API_KEY and anthropic:
            providers.append(("Anthropic", RAGEngine._stream_anthropic))

        for name, provider_fn in providers:
            yielded_any = False
            try:
                for chunk_text in provider_fn(prompt):
                    if chunk_text:
                        yielded_any = True
                        yield chunk_text
                if yielded_any:
                    return  # provider completed successfully
                logger.warning(f"{name} streaming produced no content; trying next provider.")
            except Exception as e:
                if yielded_any:
                    # Tokens already reached the client over SSE -- cannot
                    # cleanly discard them and hand off to another
                    # provider mid-stream. Propagate; the caller (chat.py)
                    # will save whatever partial text was already sent.
                    logger.error(f"{name} streaming failed mid-stream after partial output: {str(e)}")
                    raise
                logger.error(f"{name} streaming failed before yielding any tokens, trying next provider: {str(e)}")
                continue

        # Every configured provider either isn't set up or failed before
        # producing any output.
        yield RAGEngine._mock_fallback_text(chunks)

    @staticmethod
    def stream_response(
        db: Session,
        collection_name: str,
        query: str,
        conversation_history: List[Dict[str, str]] = None,
        chunks_out: List[Dict[str, Any]] = None,
    ):
        """
        Generator-based streaming counterpart to `generate_response`. Yields
        raw text deltas as they arrive from the provider (real token-level
        streaming, not an artificial word-by-word replay of an
        already-complete string).

        `chunks_out`, if provided, is populated (in place) with the
        retrieved context chunks before the first item is yielded, so the
        caller can build citations from the full accumulated text once the
        generator is exhausted via `RAGEngine.build_citations(full_text,
        chunks_out)` -- the same citation-building logic `generate_response`
        uses, applied post-hoc since citations depend on the complete `[N]`
        marker text.

        NOTE on the "knowledge boundary" safety net: `generate_response`
        additionally re-scans the *complete* response text for the phrase
        "information is not available" and, if found, discards the whole
        response in favor of the canned boundary string. That retroactive
        whole-response replacement is not reproducible here -- by the time
        the full text is available, its tokens have already been streamed
        to the client over SSE and cannot be un-sent. The only boundary
        case still honored in the streaming path is the upfront one (zero
        retrieved chunks -> emit the canned string directly without calling
        any LLM), which covers the common case. See CLAUDE.md Phase 3 entry.
        """
        chunks = RAGEngine.hybrid_search(db, collection_name, query, limit=5)
        if chunks_out is not None:
            chunks_out.extend(chunks)

        if not chunks:
            yield "The requested information is not available in the current SAP knowledge base."
            return

        prompt = RAGEngine._build_prompt(chunks, conversation_history, query)
        yield from RAGEngine._stream_llm_response(prompt, chunks)
