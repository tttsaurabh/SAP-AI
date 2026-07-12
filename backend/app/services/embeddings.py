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
            # gemini-embedding-001 is Matryoshka: we request output_dimensionality
            # equal to EMBEDDING_DIMENSION at call time, so that is the truth here
            # (default 768). Kept <=2000 so a pgvector HNSW index can be built.
            return settings.EMBEDDING_DIMENSION
        # default local all-MiniLM-L6-v2 is 384
        return 384

    @staticmethod
    def _l2_normalize(vec: List[float]) -> List[float]:
        """Unit-normalize a vector. gemini-embedding-001 returns pre-normalized
        vectors only at its native 3072 dims; Google recommends re-normalizing
        any truncated (Matryoshka) output before use."""
        arr = np.asarray(vec, dtype=np.float64)
        norm = np.linalg.norm(arr)
        if norm == 0:
            return arr.tolist()
        return (arr / norm).tolist()

    @classmethod
    def get_embeddings(cls, texts: Union[str, List[str]]) -> List[List[float]]:
        if isinstance(texts, str):
            texts = [texts]

        model_setting = settings.EMBEDDING_MODEL
        logger.info(f"Generating embeddings for {len(texts)} texts using model {model_setting}")

        # When EMBEDDING_MODEL explicitly pins a provider (e.g. "gemini:..."),
        # a failure in that provider must RAISE -- silently falling through to
        # a different provider produces vectors of a *different dimension* than
        # the stored pgvector index, which the DB then rejects and
        # supabase_db.search_similarity swallows into an empty result. That
        # exact failure mode (Gemini query vectors at 768 vs a 384-dim index)
        # turned a config change into a silent, total retrieval outage. Only an
        # unpinned model (no "<provider>:" prefix) may cascade Gemini -> local
        # -> deterministic hash for dev/no-keys convenience.
        explicit_provider = None
        for prefix in ("gemini", "openai", "local"):
            if model_setting.startswith(f"{prefix}:"):
                explicit_provider = prefix
                break

        # 1. Google Gemini Embeddings
        if explicit_provider == "gemini" or (
            explicit_provider is None
            and settings.GEMINI_API_KEY
        ):
            try:
                if not genai:
                    raise RuntimeError("google-generativeai package not available.")
                api_key = settings.GEMINI_API_KEY
                if not api_key:
                    raise RuntimeError("GEMINI_API_KEY is not set.")
                genai.configure(api_key=api_key)
                # Model name comes from the "gemini:<model>" setting (falls back
                # to the current GA embedding model). NOTE: the older
                # "text-embedding-004" is NOT served for embedContent on current
                # API keys (404) -- "gemini-embedding-001" is the GA model.
                model = model_setting.split(":", 1)[1] if ":" in model_setting else "gemini-embedding-001"
                if not model.startswith("models/"):
                    model = f"models/{model}"
                # gemini-embedding-001 is 3072-dim natively; request the configured
                # dimension so it matches the stored pgvector column and stays
                # <=2000 for indexability.
                out_dim = settings.EMBEDDING_DIMENSION
                result = genai.embed_content(
                    model=model,
                    content=texts,
                    task_type="retrieval_document",
                    output_dimensionality=out_dim,
                )
                embeddings = result["embedding"]  # list-of-lists (input is a list)
                if out_dim != 3072:
                    embeddings = [cls._l2_normalize(e) for e in embeddings]
                return embeddings
            except Exception as e:
                logger.error(f"Gemini embedding generation failed: {str(e)}")
                if explicit_provider == "gemini":
                    raise RuntimeError(
                        "EMBEDDING_MODEL is pinned to Gemini; refusing to fall "
                        f"back to a different-dimension provider: {e}"
                    ) from e

        # 2. OpenAI Embeddings
        if explicit_provider == "openai":
            try:
                if not OpenAI:
                    raise RuntimeError("openai package not available.")
                if not settings.OPENAI_API_KEY:
                    raise RuntimeError("OPENAI_API_KEY is not set.")
                client = OpenAI(api_key=settings.OPENAI_API_KEY)
                engine = model_setting.split(":", 1)[1] if ":" in model_setting else "text-embedding-3-small"
                response = client.embeddings.create(input=texts, model=engine)
                return [data.embedding for data in response.data]
            except Exception as e:
                logger.error(f"OpenAI embedding generation failed: {str(e)}")
                raise RuntimeError(
                    "EMBEDDING_MODEL is pinned to OpenAI; refusing to fall "
                    f"back to a different-dimension provider: {e}"
                ) from e

        # 3. Local SentenceTransformers Embeddings.
        # Skipped when the model is pinned to a remote provider above, so a
        # transient Gemini/OpenAI failure never silently yields 384-dim local
        # vectors against a 768/1536-dim index.
        if explicit_provider == "local" or explicit_provider is None:
            try:
                if not SentenceTransformer:
                    raise RuntimeError("sentence-transformers package not available for local embeddings.")
                if cls._local_model is None:
                    model_name = model_setting.split(":", 1)[1] if ":" in model_setting else "all-MiniLM-L6-v2"
                    logger.info(f"Loading local SentenceTransformer model: {model_name}")
                    cls._local_model = SentenceTransformer(model_name)
                embeddings = cls._local_model.encode(texts)
                return embeddings.tolist()
            except Exception as e:
                logger.error(f"Local SentenceTransformer embedding generation failed: {str(e)}")
                if explicit_provider == "local":
                    raise RuntimeError(
                        "EMBEDDING_MODEL is pinned to local sentence-transformers "
                        f"but it is unavailable: {e}"
                    ) from e

        # 4. Deterministic Hash Fallback (development/testing without keys or
        # local models only). Never used for an explicitly pinned provider --
        # those raise above rather than return wrong-dimension vectors.
        if explicit_provider is not None:
            raise RuntimeError(
                f"EMBEDDING_MODEL is pinned to '{model_setting}' but that provider "
                "is unavailable; refusing deterministic-hash fallback so a "
                "misconfiguration surfaces loudly instead of poisoning retrieval."
            )
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
