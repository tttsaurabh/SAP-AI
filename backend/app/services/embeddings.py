import hashlib
import numpy as np
from typing import List, Union
from loguru import logger
from app.core.config import settings

# Import API SDKs
try:
    import google.generativeai as genai
except ImportError:
    genai = None

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

# Import SentenceTransformers for local embeddings
try:
    from sentence_transformers import SentenceTransformer
except ImportError:
    SentenceTransformer = None

class EmbeddingsService:
    _local_model = None

    @classmethod
    def warm_up(cls) -> None:
        """
        Eagerly load the local SentenceTransformer model at process startup
        instead of lazily on the first request. Without this, the first
        chat query after every process start (including every `--reload`
        restart in dev) pays the multi-second model-load cost inline as
        part of that user-facing request (see backend/PERFORMANCE_AUDIT.md).
        No-op when a remote embedding provider is configured -- there's
        nothing local to warm.
        """
        if not settings.EMBEDDING_MODEL.startswith("local:"):
            return
        try:
            cls.get_embeddings("warm up")
            logger.info("EmbeddingsService: local model warmed up at startup.")
        except Exception as e:
            logger.warning(f"EmbeddingsService warm-up failed (will retry lazily on first request): {e}")

    @classmethod
    def get_embedding_dimension(cls) -> int:
        model_setting = settings.EMBEDDING_MODEL
        if model_setting.startswith("openai:"):
            if "large" in model_setting:
                return 3072
            return 1536
        elif model_setting.startswith("gemini:"):
            return 768
        # default local all-MiniLM-L6-v2 is 384
        return 384

    @classmethod
    def get_embeddings(cls, texts: Union[str, List[str]]) -> List[List[float]]:
        if isinstance(texts, str):
            texts = [texts]
            
        model_setting = settings.EMBEDDING_MODEL
        logger.info(f"Generating embeddings for {len(texts)} texts using model {model_setting}")

        # 1. Google Gemini Embeddings
        if model_setting.startswith("gemini:") or (settings.GEMINI_API_KEY and not model_setting.startswith("openai:") and not model_setting.startswith("local:")):
            if genai:
                try:
                    api_key = settings.GEMINI_API_KEY
                    if api_key:
                        genai.configure(api_key=api_key)
                        # Gemini default embedding model
                        model = "models/text-embedding-004"
                        result = genai.embed_content(
                            model=model,
                            content=texts,
                            task_type="retrieval_document"
                        )
                        return result['embedding']
                except Exception as e:
                    logger.error(f"Gemini embedding generation failed: {str(e)}")
            else:
                logger.warning("google-generativeai package not available.")

        # 2. OpenAI Embeddings
        if model_setting.startswith("openai:") and settings.OPENAI_API_KEY:
            if OpenAI:
                try:
                    client = OpenAI(api_key=settings.OPENAI_API_KEY)
                    engine = model_setting.split(":", 1)[1] if ":" in model_setting else "text-embedding-3-small"
                    response = client.embeddings.create(input=texts, model=engine)
                    return [data.embedding for data in response.data]
                except Exception as e:
                    logger.error(f"OpenAI embedding generation failed: {str(e)}")
            else:
                logger.warning("openai package not available.")

        # 3. Local SentenceTransformers Embeddings
        if model_setting.startswith("local:") or SentenceTransformer is not None:
            if SentenceTransformer:
                try:
                    if cls._local_model is None:
                        model_name = model_setting.split(":", 1)[1] if ":" in model_setting else "all-MiniLM-L6-v2"
                        logger.info(f"Loading local SentenceTransformer model: {model_name}")
                        cls._local_model = SentenceTransformer(model_name)
                    embeddings = cls._local_model.encode(texts)
                    return embeddings.tolist()
                except Exception as e:
                    logger.error(f"Local SentenceTransformer embedding generation failed: {str(e)}")
            else:
                logger.warning("sentence-transformers package not available for local embeddings.")

        # 4. Deterministic Hash Fallback (ensures development/testing runs smoothly without keys or local models)
        logger.warning("Using mock deterministic hash embeddings fallback.")
        dim = cls.get_embedding_dimension()
        fallback_embeddings = []
        for text in texts:
            # Create a deterministic array of floats using text hash
            hash_bytes = hashlib.sha256(text.encode('utf-8')).digest()
            # Feed state seed to numpy
            seed = int.from_bytes(hash_bytes[:4], byteorder='big')
            rng = np.random.default_rng(seed)
            vec = rng.standard_normal(dim)
            # Normalize vector to unit length
            vec = vec / np.linalg.norm(vec)
            fallback_embeddings.append(vec.tolist())
            
        return fallback_embeddings
