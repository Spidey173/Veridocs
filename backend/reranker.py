import logging
from typing import List, Dict

from config import get_model_registry, get_settings

logger = logging.getLogger(__name__)


class Reranker:
    """Scores retrieved chunks using a cross-encoder model to improve search accuracy."""

    def __init__(self):
        self.registry = get_model_registry()
        self.settings = get_settings()

    def rerank(
        self,
        query: str,
        chunks: List[Dict],
        top_k: int = None
    ) -> List[Dict]:
        """Re-rank candidate chunks against the query and return the top results."""
        if top_k is None:
            top_k = self.settings.RETRIEVAL_FINAL_K

        if not chunks:
            return []

        if len(chunks) <= top_k:
            return chunks

        model = self.registry.reranker_model

        if model is None:
            logger.warning("Reranker model not available, returning chunks as-is")
            return chunks[:top_k]

        try:
            doc_texts = [chunk["text"] for chunk in chunks]

            # FastEmbed CrossEncoder
            if hasattr(model, "rerank") and callable(getattr(model, "rerank")):
                reranked_items = list(model.rerank(query, doc_texts))
                scored_chunks = []
                for item in reranked_items:
                    idx = item["index"] if isinstance(item, dict) else getattr(item, "index", None)
                    score = item["score"] if isinstance(item, dict) else getattr(item, "score", 0.0)
                    if idx is not None and 0 <= idx < len(chunks):
                        c = chunks[idx].copy()
                        c["rerank_score"] = float(score)
                        scored_chunks.append(c)

                if scored_chunks:
                    scored_chunks.sort(key=lambda x: x["rerank_score"], reverse=True)
                    return scored_chunks[:top_k]

            # SentenceTransformers cross-encoder
            if hasattr(model, "predict") and callable(getattr(model, "predict")):
                pairs = [(query, text) for text in doc_texts]
                try:
                    scores = model.predict(pairs, show_progress_bar=False)
                except TypeError:
                    scores = model.predict(pairs)

                scored_chunks = []
                for chunk, score in zip(chunks, scores):
                    chunk_copy = chunk.copy()
                    chunk_copy["rerank_score"] = float(score)
                    scored_chunks.append(chunk_copy)

                scored_chunks.sort(key=lambda x: x["rerank_score"], reverse=True)
                return scored_chunks[:top_k]

            return chunks[:top_k]

        except Exception as e:
            logger.error(f"Re-ranking failed: {e}. Returning unranked results.")
            return chunks[:top_k]


def rerank_chunks(query: str, chunks: List[Dict], top_k: int = None) -> List[Dict]:
    """Helper to re-rank chunks using Reranker."""
    reranker = Reranker()
    return reranker.rerank(query, chunks, top_k)
