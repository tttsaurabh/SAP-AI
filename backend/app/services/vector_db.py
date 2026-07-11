from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels
from qdrant_client.http.exceptions import UnexpectedResponse
from typing import List, Dict, Any, Optional
from loguru import logger
from app.core.config import settings
from app.services.embeddings import EmbeddingsService

class VectorDBService:
    _client = None

    @classmethod
    def get_client(cls) -> QdrantClient:
        if cls._client is None:
            # Try to connect to Qdrant Docker host
            try:
                logger.info(f"Connecting to Qdrant at {settings.QDRANT_HOST}:{settings.QDRANT_PORT}")
                client = QdrantClient(host=settings.QDRANT_HOST, port=settings.QDRANT_PORT, timeout=5.0)
                # Verify connection
                client.get_collections()
                cls._client = client
                logger.info("Connected to remote Qdrant container successfully.")
            except Exception as e:
                logger.warning(f"Failed to connect to remote Qdrant ({str(e)}). Falling back to local in-memory Qdrant instance.")
                # Local memory fallback client
                cls._client = QdrantClient(location=":memory:")
        return cls._client

    @classmethod
    def create_collection_if_not_exists(cls, collection_name: str):
        client = cls.get_client()
        dim = EmbeddingsService.get_embedding_dimension()
        
        try:
            client.get_collection(collection_name)
            logger.info(f"Collection '{collection_name}' already exists.")
        except (UnexpectedResponse, Exception):
            logger.info(f"Creating collection '{collection_name}' with vector size {dim}")
            client.create_collection(
                collection_name=collection_name,
                vectors_config=qmodels.VectorParams(
                    size=dim,
                    distance=qmodels.Distance.COSINE
                )
            )

    @classmethod
    def upsert_chunks(cls, collection_name: str, document_id: int, filename: str, chunks: List[Dict[str, Any]]):
        cls.create_collection_if_not_exists(collection_name)
        client = cls.get_client()
        
        # Prepare vectors
        texts = [chunk["text"] for chunk in chunks]
        embeddings = EmbeddingsService.get_embeddings(texts)
        
        points = []
        for idx, chunk in enumerate(chunks):
            # Qdrant requires points containing id (int/uuid), vector (list[float]), payload (dict)
            point_id = document_id * 100000 + chunk["chunk_index"]
            payload = {
                "document_id": document_id,
                "filename": filename,
                "text": chunk["text"],
                "page_number": chunk.get("page_number", 1),
                "section_header": chunk.get("section_header", ""),
                "collection_name": collection_name
            }
            points.append(
                qmodels.PointStruct(
                    id=point_id,
                    vector=embeddings[idx],
                    payload=payload
                )
            )
            
        logger.info(f"Upserting {len(points)} points into Qdrant collection '{collection_name}'")
        client.upsert(collection_name=collection_name, points=points)

    @classmethod
    def delete_document_vectors(cls, collection_name: str, document_id: int):
        client = cls.get_client()
        try:
            client.delete(
                collection_name=collection_name,
                points_selector=qmodels.Filter(
                    must=[
                        qmodels.FieldCondition(
                            key="document_id",
                            match=qmodels.MatchValue(value=document_id)
                        )
                    ]
                )
            )
            logger.info(f"Deleted vectors for document ID {document_id} from collection '{collection_name}'")
        except Exception as e:
            logger.error(f"Failed to delete document vectors: {str(e)}")

    @classmethod
    def search_similarity(cls, collection_name: str, query: str, limit: int = 5, document_id: Optional[int] = None) -> List[Dict[str, Any]]:
        cls.create_collection_if_not_exists(collection_name)
        client = cls.get_client()
        
        query_vector = EmbeddingsService.get_embeddings(query)[0]
        
        # Build filter if document_id is supplied
        q_filter = None
        if document_id is not None:
            q_filter = qmodels.Filter(
                must=[
                    qmodels.FieldCondition(
                        key="document_id",
                        match=qmodels.MatchValue(value=document_id)
                    )
                ]
            )
            
        try:
            response = client.query_points(
                collection_name=collection_name,
                query=query_vector,
                query_filter=q_filter,
                limit=limit
            )
            
            search_hits = []
            for hit in response.points:
                payload = hit.payload
                search_hits.append({
                    "score": hit.score,
                    "text": payload.get("text", ""),
                    "document_id": payload.get("document_id"),
                    "filename": payload.get("filename", ""),
                    "page_number": payload.get("page_number", 1),
                    "section_header": payload.get("section_header", ""),
                    "collection_name": payload.get("collection_name", "")
                })
            return search_hits
        except Exception as e:
            logger.error(f"Error searching Qdrant collection: {str(e)}")
            return []
Class = VectorDBService
