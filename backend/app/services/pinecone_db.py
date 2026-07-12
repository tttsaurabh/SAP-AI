"""
PineconeDBService — wraps Pinecone SDK with the same interface as VectorDBService.
Namespaces in Pinecone map to collection_name (e.g. "Default").
"""

import time
from typing import List, Dict, Any, Optional
from loguru import logger
from app.core.config import settings
from app.services.embeddings import EmbeddingsService

try:
    from pinecone import Pinecone, ServerlessSpec
except ImportError:
    Pinecone = None
    ServerlessSpec = None


class PineconeDBService:
    _client = None
    _index = None

    # ------------------------------------------------------------------ #
    #  Client / Index initialisation                                       #
    # ------------------------------------------------------------------ #

    @classmethod
    def get_client(cls) -> "Pinecone":
        if cls._client is None:
            if Pinecone is None:
                raise ImportError("pinecone-client package not installed. Run: pip install pinecone-client>=3.2.2")
            api_key = settings.PINECONE_API_KEY
            if not api_key:
                raise ValueError("PINECONE_API_KEY is not set in environment/.env")
            cls._client = Pinecone(api_key=api_key)
            logger.info("Pinecone client initialised.")
        return cls._client

    @classmethod
    def get_index(cls):
        if cls._index is None:
            pc = cls.get_client()
            index_name = settings.PINECONE_INDEX_NAME
            dim = EmbeddingsService.get_embedding_dimension()

            existing = [idx.name for idx in pc.list_indexes()]
            if index_name not in existing:
                logger.info(f"Creating Pinecone serverless index '{index_name}' (dim={dim}) ...")
                pc.create_index(
                    name=index_name,
                    dimension=dim,
                    metric="cosine",
                    spec=ServerlessSpec(cloud="aws", region="us-east-1"),
                )
                # Wait for index to be ready
                for _ in range(30):
                    status = pc.describe_index(index_name).status
                    if status.get("ready", False):
                        break
                    logger.info("Waiting for Pinecone index to be ready...")
                    time.sleep(3)
            else:
                logger.info(f"Pinecone index '{index_name}' already exists.")

            cls._index = pc.Index(index_name)
            logger.info(f"Connected to Pinecone index '{index_name}'.")
        return cls._index

    # ------------------------------------------------------------------ #
    #  Upsert chunks                                                       #
    # ------------------------------------------------------------------ #

    @classmethod
    def upsert_chunks(
        cls,
        collection_name: str,
        document_id: int,
        filename: str,
        chunks: List[Dict[str, Any]],
        batch_size: int = 100,
    ):
        """
        Embeds and upserts chunk vectors into Pinecone.
        Uses `collection_name` as the Pinecone namespace.
        """
        index = cls.get_index()
        namespace = collection_name

        texts = [c["text"] for c in chunks]
        embeddings = EmbeddingsService.get_embeddings(texts)

        vectors = []
        for i, chunk in enumerate(chunks):
            # vector_id is generated once upstream (app/api/documents.py upload flow) and reused
            # here and on the Chunk.vector_id column -- this backend does not derive its own id
            # formula. Fall back to the historical formula only for callers that don't supply one.
            vector_id = chunk.get("vector_id") or f"doc{document_id}_chunk{chunk['chunk_index']}"
            metadata = {
                "document_id": document_id,
                "filename": filename,
                "text": chunk["text"][:2000],   # Pinecone metadata value limit
                "page_number": chunk.get("page_number", 1),
                "section_header": chunk.get("section_header", ""),
                "collection_name": collection_name,
                "chunk_id": chunk.get("chunk_id"),
                "chunk_index": chunk.get("chunk_index")
            }
            vectors.append({"id": vector_id, "values": embeddings[i], "metadata": metadata})

        # Batch upsert
        for start in range(0, len(vectors), batch_size):
            batch = vectors[start : start + batch_size]
            index.upsert(vectors=batch, namespace=namespace)
            logger.info(
                f"Upserted batch {start // batch_size + 1} "
                f"({len(batch)} vectors) into Pinecone namespace '{namespace}'"
            )

        logger.info(
            f"Upserted {len(vectors)} total vectors for document '{filename}' into Pinecone."
        )

    # ------------------------------------------------------------------ #
    #  Similarity search                                                   #
    # ------------------------------------------------------------------ #

    @classmethod
    def search_similarity(
        cls,
        collection_name: str,
        query: str,
        limit: int = 5,
        document_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        index = cls.get_index()
        namespace = collection_name

        query_vector = EmbeddingsService.get_embeddings(query)[0]

        # Optional metadata filter by document_id
        pf = None
        if document_id is not None:
            pf = {"document_id": {"$eq": document_id}}

        try:
            response = index.query(
                vector=query_vector,
                top_k=limit,
                namespace=namespace,
                include_metadata=True,
                filter=pf,
            )

            results = []
            for match in response.get("matches", []):
                meta = match.get("metadata", {})
                results.append({
                    "score": match.get("score", 0.0),
                    "text": meta.get("text", ""),
                    "document_id": meta.get("document_id"),
                    "filename": meta.get("filename", ""),
                    "page_number": meta.get("page_number", 1),
                    "section_header": meta.get("section_header", ""),
                    "collection_name": meta.get("collection_name", collection_name),
                    "chunk_id": meta.get("chunk_id"),
                    "chunk_index": meta.get("chunk_index")
                })
            logger.info(
                f"Pinecone search in namespace '{namespace}' returned {len(results)} results."
            )
            return results
        except Exception as e:
            logger.error(f"Pinecone search failed: {str(e)}")
            return []

    # ------------------------------------------------------------------ #
    #  Delete document vectors                                             #
    # ------------------------------------------------------------------ #

    @classmethod
    def delete_document_vectors(cls, collection_name: str, document_id: int):
        index = cls.get_index()
        namespace = collection_name
        try:
            index.delete(
                filter={"document_id": {"$eq": document_id}},
                namespace=namespace,
            )
            logger.info(
                f"Deleted Pinecone vectors for document_id={document_id} in namespace '{namespace}'."
            )
        except Exception as e:
            logger.error(f"Pinecone delete failed: {str(e)}")
