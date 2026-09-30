"""
Cross-Encoder Re-ranking module for DocuMind AI.
Re-ranks retrieved candidates using a more powerful cross-encoder model
for significantly improved precision.
"""

import logging
from typing import List, Dict, Tuple

from config import get_model_registry, get_settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class Reranker:
    """
    Re-ranks retrieved document chunks using a cross-encoder model.

    Pipeline:
    1. Receive query + candidate chunks (typically top 20 from hybrid search)
    2. Score each (query, chunk) pair with cross-encoder
    3. Sort by cross-encoder score
    4. Return top-K (typically 5)
    """

    def __init__(self):
        self.registry = get_model_registry()
        self.settings = get_settings()

    def rerank(
        self,
        query: str,
        chunks: List[Dict],
        top_k: int = None
    ) -> List[Dict]:
        """
        Re-rank chunks using cross-encoder model.

        Args:
            query: The user's question
            chunks: List of candidate chunks from retrieval
            top_k: Number of top results to return (default from settings)

        Returns:
            Re-ranked list of top-K chunks with added 'rerank_score'
        """
        if top_k is None:
            top_k = self.settings.RETRIEVAL_FINAL_K

        if not chunks:
            return []

        # If fewer chunks than top_k, just return them all
        if len(chunks) <= top_k:
            return chunks

        model = self.registry.reranker_model

        if model is None:
            logger.warning("Reranker model not available, returning chunks as-is")
            return chunks[:top_k]

        try:
            doc_texts = [chunk["text"] for chunk in chunks]

            # FastEmbed TextCrossEncoder uses .rerank(query, documents)
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
                    logger.debug(f"FastEmbed re-ranked {len(chunks)} chunks → top {top_k}")
                    return scored_chunks[:top_k]

            # SentenceTransformers or test mocks use .predict(pairs)
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
                logger.debug(
                    f"Re-ranked {len(chunks)} chunks → top {top_k}. "
                    f"Score range: [{scored_chunks[-1]['rerank_score']:.3f}, {scored_chunks[0]['rerank_score']:.3f}]"
                )
                return scored_chunks[:top_k]

            # Fallback if no matching method
            return chunks[:top_k]

        except Exception as e:
            logger.error(f"Re-ranking failed: {e}. Returning un-re-ranked results.")
            return chunks[:top_k]


def rerank_chunks(query: str, chunks: List[Dict], top_k: int = None) -> List[Dict]:
    """
    Convenience function for re-ranking.
    Creates a Reranker instance and re-ranks the chunks.
    """
    reranker = Reranker()
    return reranker.rerank(query, chunks, top_k)
