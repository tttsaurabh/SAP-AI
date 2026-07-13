import hashlib
import threading
import time
from collections import deque
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
    # gemini-embedding-001 caps items per embed_content request (~100); larger
    # requests return ResourceExhausted. Keep sub-batches at/under this.
    _GEMINI_EMBED_BATCH = 100
    # Free-tier rate limit: 100 embeddings/minute. Throttle to 90/min (1.5s per item).
    _GEMINI_RATE_LIMIT_PER_SEC = 90.0 / 60.0  # items per second
    _gemini_rate_tokens = deque(maxlen=100)
    _gemini_rate_lock = threading.Lock()

    @classmethod
    def _rate_limit_gemini(cls, num_items: int) -> None:
        """Throttle Gemini embedding calls to stay under 100/min free-tier quota."""
        now = time.time()
        with cls._gemini_rate_lock:
            # Remove tokens older than 60 seconds
            while cls._gemini_rate_tokens and cls._gemini_rate_tokens[0] < now - 60:
                cls._gemini_rate_tokens.popleft()
            # Check if adding num_items would exceed the 90/min target
            if len(cls._gemini_rate_tokens) + num_items > 90:
                # Sleep until oldest token is 60s old
                sleep_until = cls._gemini_rate_tokens[0] + 60
                delay = max(0, sleep_until - now)
                if delay > 0:
                    logger.info(f"Rate-limiting: sleeping {delay:.1f}s to stay under 100/min quota")
                    time.sleep(delay)
            # Record this batch
            for _ in range(num_items):
                cls._gemini_rate_tokens.append(time.time())

    @staticmethod
    def _gemini_embed_with_retry(model: str, texts: List[str], out_dim: int, attempts: int = 3):
        """Call genai.embed_content with a short exponential backoff so a
        transient per-minute rate-limit (ResourceExhausted) during a bulk
        re-ingest is retried rather than failing the whole document."""
        import time as _time
        last_exc = None
        for i in range(attempts):
            try:
                return genai.embed_content(
                    model=model,
                    content=texts,
                    task_type="retrieval_document",
                    output_dimensionality=out_dim,
                )
            except Exception as e:  # noqa: BLE001 -- retried/re-raised below
                last_exc = e
                if "ResourceExhausted" in type(e).__name__ or "429" in str(e):
                    _time.sleep(2 ** i)  # 1s, 2s, 4s
                    continue
                raise
        raise last_exc if last_exc else RuntimeError("Gemini embedding failed after retries")

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
                # gemini-embedding-001 rejects large per-request batches
                # (ResourceExhausted above ~100 items), so split into sub-batches.
                # Apply free-tier rate limiting (90/min) between batches.
                embeddings: List[List[float]] = []
                for start in range(0, len(texts), cls._GEMINI_EMBED_BATCH):
                    sub = texts[start:start + cls._GEMINI_EMBED_BATCH]
                    cls._rate_limit_gemini(len(sub))
                    result = cls._gemini_embed_with_retry(model, sub, out_dim)
                    vecs = result["embedding"]
                    # embed_content returns a flat list for a single-string input
                    # and a list-of-lists for a list input; `sub` is always a list,
                    # but guard the single-item case defensively.
                    if vecs and not isinstance(vecs[0], (list, tuple)):
                        vecs = [vecs]
                    if out_dim != 3072:
                        vecs = [cls._l2_normalize(v) for v in vecs]
                    embeddings.extend(vecs)
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
