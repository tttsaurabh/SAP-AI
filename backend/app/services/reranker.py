from typing import List, Dict, Any
from loguru import logger
from app.core.config import settings

# Import CrossEncoder with fallback, mirroring the SentenceTransformer
# import-with-fallback pattern in embeddings.py.
try:
    from sentence_transformers import CrossEncoder
except ImportError:
    CrossEncoder = None


class Reranker:
    """
    Cross-encoder reranking of RAG candidate chunks (Phase 4 non-security
    remediation). `settings.RERANK_ENABLED` / `settings.RERANK_MODEL`
    previously existed in `core/config.py` and `.env.example` as dead
    config -- grep confirmed zero references anywhere outside config.py
    before this module was added. This is what actually consumes them now.

    Lazily loads and caches a `sentence_transformers.CrossEncoder` model as
    a class-level singleton, mirroring the exact caching pattern
    `EmbeddingsService._local_model` uses in `embeddings.py` for the local
    `SentenceTransformer` embedding fallback (lazy `classmethod`-guarded
    load on first use, cached on the class thereafter).
    """

    _model = None
    _model_name = None

    # Used when RERANK_ENABLED is true but RERANK_MODEL is left blank.
    DEFAULT_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"

    @classmethod
    def _get_model(cls):
        model_name = settings.RERANK_MODEL or cls.DEFAULT_MODEL
        if cls._model is None or cls._model_name != model_name:
            # One-time warning on first load (or a model-name change) about
            # latency, mirroring embeddings.py's `logger.info` on first
            # local SentenceTransformer load -- upgraded to `warning` here
            # since a cross-encoder scoring every (query, candidate) pair
            # is a heavier, more latency-visible operation than a single
            # embedding call.
            logger.warning(
                f"Loading cross-encoder reranker model '{model_name}' for "
                f"the first time -- this can take several seconds (or "
                f"longer, including a one-time download) and adds latency "
                f"to this request. The model is cached for all subsequent "
                f"requests in this process."
            )
            cls._model = CrossEncoder(model_name)
            cls._model_name = model_name
        return cls._model

    @classmethod
    def rerank(cls, query: str, candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Scores each candidate's `text` field against `query` via the
        cross-encoder (`model.predict([(query, candidate["text"]), ...])`)
        and returns the candidates sorted descending by score. All existing
        dict keys on each candidate dict are preserved; a `rerank_score`
        key is added (or overwritten) with the model's raw score.

        No-ops (returns `candidates` unchanged, same order) when:
        - `settings.RERANK_ENABLED` is false -- reranking must be a no-op
          when the flag is off, matching how it already existed as an
          unused toggle in config before this module was added.
        - fewer than 2 candidates were passed (nothing to reorder).
        - `sentence_transformers` isn't installed in this environment.
        - model loading or scoring raises for any reason -- reranking is a
          relevance *enhancement* on top of RRF fusion, never a hard
          dependency for RAG retrieval to keep functioning.
        """
        if not settings.RERANK_ENABLED:
            return candidates
        if not candidates or len(candidates) < 2:
            return candidates
        if CrossEncoder is None:
            logger.warning(
                "RERANK_ENABLED is true but sentence-transformers is not "
                "installed; skipping reranking and returning RRF-fused "
                "order unchanged."
            )
            return candidates

        try:
            model = cls._get_model()
            pairs = [(query, candidate.get("text", "") or "") for candidate in candidates]
            scores = model.predict(pairs)
            for candidate, score in zip(candidates, scores):
                candidate["rerank_score"] = float(score)
            return sorted(candidates, key=lambda c: c["rerank_score"], reverse=True)
        except Exception as e:
            logger.error(f"Cross-encoder reranking failed, falling back to RRF-fused order: {str(e)}")
            return candidates
