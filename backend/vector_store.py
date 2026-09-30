"""
Hybrid Vector Store for DocuMind AI.
Combines dense retrieval (FAISS) with sparse retrieval (BM25)
and fuses results using Reciprocal Rank Fusion (RRF).
"""

import logging
import math
import re
import json
from pathlib import Path
from collections import defaultdict
from typing import List, Dict, Optional, Tuple

import faiss
import numpy as np

from config import get_model_registry, get_settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global in-memory cache for query embeddings to avoid redundant FastEmbed ONNX inference
_QUERY_CACHE: Dict[str, np.ndarray] = {}
_MAX_QUERY_CACHE_SIZE = 512



# ──────────────────────────────────────────────
# BM25 Sparse Retriever
# ──────────────────────────────────────────────

class BM25:
    """
    Lightweight BM25 implementation for sparse keyword retrieval.
    Used alongside dense retrieval for hybrid search.
    """

    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.doc_count = 0
        self.avg_doc_len = 0.0
        self.doc_lengths: List[int] = []
        self.doc_freqs: Dict[str, int] = defaultdict(int)  # term → num docs containing it
        self.term_freqs: List[Dict[str, int]] = []  # per-doc term frequencies
        self.corpus_size = 0

    @staticmethod
    def _tokenize(text: str) -> List[str]:
        """Simple whitespace + lowercasing tokenizer."""
        text = text.lower()
        text = re.sub(r'[^\w\s]', ' ', text)
        return [t for t in text.split() if len(t) > 1]

    def fit(self, documents: List[str]):
        """Index a corpus of documents."""
        self.doc_count = len(documents)
        self.term_freqs = []
        self.doc_lengths = []
        self.doc_freqs = defaultdict(int)

        for doc in documents:
            tokens = self._tokenize(doc)
            self.doc_lengths.append(len(tokens))

            tf: Dict[str, int] = defaultdict(int)
            seen_terms = set()
            for token in tokens:
                tf[token] += 1
                if token not in seen_terms:
                    self.doc_freqs[token] += 1
                    seen_terms.add(token)

            self.term_freqs.append(dict(tf))

        self.avg_doc_len = sum(self.doc_lengths) / max(self.doc_count, 1)
        self.corpus_size = self.doc_count
        logger.debug(f"BM25: indexed {self.doc_count} documents, {len(self.doc_freqs)} unique terms")

    def search(self, query: str, k: int = 20) -> List[Tuple[int, float]]:
        """
        Score all documents against query and return top-k (index, score) pairs.
        """
        query_tokens = self._tokenize(query)
        scores = []

        for doc_idx in range(self.doc_count):
            score = 0.0
            doc_len = self.doc_lengths[doc_idx]
            tf_dict = self.term_freqs[doc_idx]

            for term in query_tokens:
                if term not in tf_dict:
                    continue

                tf = tf_dict[term]
                df = self.doc_freqs.get(term, 0)

                # IDF with smoothing
                idf = math.log((self.doc_count - df + 0.5) / (df + 0.5) + 1.0)

                # BM25 TF normalization
                tf_norm = (tf * (self.k1 + 1)) / (
                    tf + self.k1 * (1 - self.b + self.b * doc_len / max(self.avg_doc_len, 1))
                )

                score += idf * tf_norm

            scores.append((doc_idx, score))

        # Sort by score descending
        scores.sort(key=lambda x: x[1], reverse=True)
        return scores[:k]


# ──────────────────────────────────────────────
# Reciprocal Rank Fusion
# ──────────────────────────────────────────────

def reciprocal_rank_fusion(
    rankings: List[List[Tuple[int, float]]],
    weights: Optional[List[float]] = None,
    k: int = 60
) -> List[Tuple[int, float]]:
    """
    Merge multiple ranked lists using Reciprocal Rank Fusion.

    Args:
        rankings: List of ranked results, each is [(doc_idx, score), ...]
        weights: Optional weight for each ranking list
        k: RRF constant (higher = more weight to lower-ranked items)

    Returns:
        Fused ranking as [(doc_idx, fused_score), ...]
    """
    if weights is None:
        weights = [1.0] * len(rankings)

    fused_scores: Dict[int, float] = defaultdict(float)

    for ranking, weight in zip(rankings, weights):
        for rank, (doc_idx, _score) in enumerate(ranking):
            fused_scores[doc_idx] += weight / (k + rank + 1)

    # Sort by fused score descending
    result = sorted(fused_scores.items(), key=lambda x: x[1], reverse=True)
    return result


# ──────────────────────────────────────────────
# Hybrid Vector Store
# ──────────────────────────────────────────────

class VectorStore:
    """
    Hybrid retrieval store combining:
    1. Dense retrieval via FAISS (semantic similarity)
    2. Sparse retrieval via BM25 (keyword matching)
    3. Reciprocal Rank Fusion to merge results
    """

    def __init__(self):
        self.registry = get_model_registry()
        self.settings = get_settings()

        self.index = None
        self.chunks: List[Dict] = []
        self.embeddings = None
        self.bm25 = BM25()
        self._bm25_fitted = False

    def add_documents(self, chunks: List[Dict]):
        """Index documents for both dense and sparse retrieval."""
        if not chunks:
            logger.warning("No chunks to add")
            return

        try:
            texts = [c["text"] for c in chunks]
            logger.info(f"Generating embeddings for {len(texts)} chunks...")

            # Dense indexing: encode all texts into embeddings
            model = self.registry.embedding_model
            self.embeddings = model.encode(
                texts,
                convert_to_numpy=True,
                show_progress_bar=False,
                batch_size=self.settings.EMBEDDING_BATCH_SIZE
            )

            dimension = self.embeddings.shape[1]
            self.index = faiss.IndexFlatIP(dimension)  # Inner product for cosine similarity

            # Normalize embeddings for cosine similarity
            faiss.normalize_L2(self.embeddings)
            self.index.add(self.embeddings)

            # Sparse indexing: fit BM25
            self.bm25.fit(texts)
            self._bm25_fitted = True

            self.chunks.extend(chunks)
            logger.info(f"Successfully indexed {len(chunks)} chunks (dense + sparse)")

        except Exception as e:
            logger.error(f"Error adding documents to vector store: {e}")
            raise

    def search(self, query: str, k: int = 5) -> List[Dict]:
        """
        Hybrid search: combine dense and sparse retrieval with RRF.

        Pipeline:
        1. Dense search → top RETRIEVAL_INITIAL_K candidates
        2. BM25 search → top RETRIEVAL_INITIAL_K candidates
        3. RRF fusion → merged ranking
        4. Return top k results
        """
        if self.index is None:
            logger.warning("Search attempted on empty index")
            return []

        initial_k = self.settings.RETRIEVAL_INITIAL_K

        try:
            # === Dense Retrieval with In-Memory Query Embedding Cache ===
            query_norm = query.strip().lower()
            if query_norm in _QUERY_CACHE:
                query_embedding = _QUERY_CACHE[query_norm].copy()
            else:
                model = self.registry.embedding_model
                query_embedding = model.encode(
                    [query],
                    convert_to_numpy=True
                )
                faiss.normalize_L2(query_embedding)
                if len(_QUERY_CACHE) >= _MAX_QUERY_CACHE_SIZE:
                    first_key = next(iter(_QUERY_CACHE))
                    del _QUERY_CACHE[first_key]
                _QUERY_CACHE[query_norm] = query_embedding.copy()

            distances, indices = self.index.search(query_embedding, min(initial_k, len(self.chunks)))

            dense_results = []
            for idx, dist in zip(indices[0], distances[0]):
                if 0 <= idx < len(self.chunks):
                    dense_results.append((int(idx), float(dist)))

            # === Sparse Retrieval (BM25) ===
            sparse_results = []
            if self._bm25_fitted:
                sparse_results = self.bm25.search(query, k=initial_k)

            # === Reciprocal Rank Fusion ===
            rankings = [dense_results]
            weights = [self.settings.DENSE_WEIGHT]

            if sparse_results:
                rankings.append(sparse_results)
                weights.append(self.settings.BM25_WEIGHT)

            fused = reciprocal_rank_fusion(
                rankings,
                weights=weights,
                k=self.settings.RRF_K
            )

            # Take top k results
            top_indices = [idx for idx, _score in fused[:k]]

            results = []
            for idx in top_indices:
                if 0 <= idx < len(self.chunks):
                    chunk = self.chunks[idx].copy()
                    # Add relevance score from RRF
                    rrf_score = next((s for i, s in fused if i == idx), 0.0)
                    chunk["relevance_score"] = rrf_score
                    results.append(chunk)

            logger.debug(
                f"Hybrid search: {len(dense_results)} dense + {len(sparse_results)} sparse "
                f"→ {len(results)} results after RRF"
            )
            return results

        except Exception as e:
            logger.error(f"Error during search: {e}")
            return []

    def search_dense_only(self, query: str, k: int = 5) -> List[Dict]:
        """Fallback: dense-only search (original behavior)."""
        if self.index is None:
            return []

        try:
            query_norm = query.strip().lower()
            if query_norm in _QUERY_CACHE:
                query_embedding = _QUERY_CACHE[query_norm].copy()
            else:
                model = self.registry.embedding_model
                query_embedding = model.encode([query], convert_to_numpy=True)
                faiss.normalize_L2(query_embedding)
                if len(_QUERY_CACHE) >= _MAX_QUERY_CACHE_SIZE:
                    del _QUERY_CACHE[next(iter(_QUERY_CACHE))]
                _QUERY_CACHE[query_norm] = query_embedding.copy()

            distances, indices = self.index.search(query_embedding, k)

            results = []
            for idx in indices[0]:
                if 0 <= idx < len(self.chunks):
                    results.append(self.chunks[idx])

            return results

        except Exception as e:
            logger.error(f"Error during dense search: {e}")
            return []

    def save_to_disk(self, directory: Path):
        """
        Serialize the FAISS index and chunk metadata to disk.
        Allows instant session restoration across server restarts without re-embedding.
        """
        try:
            directory.mkdir(parents=True, exist_ok=True)
            if self.index is not None:
                index_path = directory / "faiss.index"
                faiss.write_index(self.index, str(index_path))

            manifest_path = directory / "manifest.json"
            manifest = {
                "chunk_count": len(self.chunks),
                "chunks": self.chunks,
                "_bm25_fitted": self._bm25_fitted,
            }
            with open(manifest_path, "w", encoding="utf-8") as f:
                json.dump(manifest, f)
            logger.info(f"Successfully saved VectorStore ({len(self.chunks)} chunks) to {directory}")
        except Exception as e:
            logger.error(f"Failed to save VectorStore to {directory}: {e}")

    @classmethod
    def load_from_disk(cls, directory: Path) -> Optional["VectorStore"]:
        """
        Deserialize pre-computed FAISS index and chunk metadata from disk.
        """
        manifest_path = directory / "manifest.json"
        index_path = directory / "faiss.index"

        if not manifest_path.exists():
            return None

        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                manifest = json.load(f)

            store = cls()
            store.chunks = manifest.get("chunks", [])

            if index_path.exists():
                store.index = faiss.read_index(str(index_path))

            # Fast BM25 rebuild from loaded chunks
            texts = [c["text"] for c in store.chunks]
            if texts:
                store.bm25.fit(texts)
                store._bm25_fitted = True

            logger.info(f"Restored VectorStore from {directory} ({len(store.chunks)} chunks)")
            return store
        except Exception as e:
            logger.error(f"Failed to load VectorStore from {directory}: {e}")
            return None