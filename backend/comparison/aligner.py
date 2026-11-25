"""
Clause Aligner and Diff Engine for Veridocs.
Aligns contract clauses between two documents using:
1. Exact Number / Heading Matching
2. Scipy Hungarian Algorithm (linear_sum_assignment) on Dense Embedding Cosine Similarity
3. Difflib Word-Level Diff and Change Classification (unchanged, modified, added, removed, moved)
"""

import difflib
import logging
from typing import List, Dict, Any, Optional, Set
import numpy as np
from scipy.optimize import linear_sum_assignment

from config import get_settings

logger = logging.getLogger(__name__)


def compute_cosine_similarity(emb_a: List[float], emb_b: List[float]) -> float:
    """Computes cosine similarity between two 384-dimensional vectors."""
    if not emb_a or not emb_b:
        return 0.0
    a = np.array(emb_a, dtype=np.float32)
    b = np.array(emb_b, dtype=np.float32)
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a < 1e-6 or norm_b < 1e-6:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))


def compute_word_diff(text_a: str, text_b: str) -> List[Dict[str, str]]:
    """
    Computes fine-grained word-level diff between text_a and text_b.
    Returns list of tokens with tags: 'equal', 'insert' (added in B), 'delete' (removed from A).
    """
    words_a = text_a.split()
    words_b = text_b.split()

    matcher = difflib.SequenceMatcher(None, words_a, words_b)
    diff_tokens: List[Dict[str, str]] = []

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            diff_tokens.append({"type": "equal", "text": " ".join(words_a[i1:i2])})
        elif tag == "replace":
            diff_tokens.append({"type": "delete", "text": " ".join(words_a[i1:i2])})
            diff_tokens.append({"type": "insert", "text": " ".join(words_b[j1:j2])})
        elif tag == "delete":
            diff_tokens.append({"type": "delete", "text": " ".join(words_a[i1:i2])})
        elif tag == "insert":
            diff_tokens.append({"type": "insert", "text": " ".join(words_b[j1:j2])})

    return diff_tokens


class ClauseAligner:
    """Aligns and diffs clauses between two versions of a contract."""

    def __init__(self, similarity_threshold: Optional[float] = None):
        settings = get_settings()
        self.threshold = similarity_threshold or settings.COMPARISON_SIMILARITY_THRESHOLD

    def align_and_diff(self, clauses_a: List[Dict[str, Any]], clauses_b: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Align clauses from document A and document B and generate classified diffs.
        """
        aligned_results: List[Dict[str, Any]] = []

        matched_a_indices: Set[int] = set()
        matched_b_indices: Set[int] = set()

        # Step 1: Direct Number and Heading Exact Matching
        for idx_a, ca in enumerate(clauses_a):
            num_a = (ca.get("number") or "").strip().lower()
            head_a = (ca.get("heading") or "").strip().lower()

            if not num_a and not head_a:
                continue

            for idx_b, cb in enumerate(clauses_b):
                if idx_b in matched_b_indices:
                    continue

                num_b = (cb.get("number") or "").strip().lower()
                head_b = (cb.get("heading") or "").strip().lower()

                # Strong match on number or heading
                is_num_match = num_a and num_b and (num_a == num_b) and num_a not in ("preamble", "1")
                is_head_match = head_a and head_b and (head_a == head_b) and len(head_a) >= 4

                if is_num_match or is_head_match:
                    matched_a_indices.add(idx_a)
                    matched_b_indices.add(idx_b)

                    diff_entry = self._build_pair_diff(ca, cb, idx_a, idx_b)
                    aligned_results.append(diff_entry)
                    break

        # Step 2: Hungarian Algorithm (linear_sum_assignment) on Remaining Clauses
        unmatched_a = [i for i in range(len(clauses_a)) if i not in matched_a_indices]
        unmatched_b = [j for j in range(len(clauses_b)) if j not in matched_b_indices]

        if unmatched_a and unmatched_b:
            # Build cost matrix: cost = 1.0 - cosine_similarity
            cost_matrix = np.zeros((len(unmatched_a), len(unmatched_b)), dtype=np.float32)

            for row_idx, idx_a in enumerate(unmatched_a):
                emb_a = clauses_a[idx_a].get("embedding")
                for col_idx, idx_b in enumerate(unmatched_b):
                    emb_b = clauses_b[idx_b].get("embedding")
                    sim = compute_cosine_similarity(emb_a, emb_b)
                    cost_matrix[row_idx, col_idx] = 1.0 - sim

            row_ind, col_ind = linear_sum_assignment(cost_matrix)

            for r, c in zip(row_ind, col_ind):
                idx_a = unmatched_a[r]
                idx_b = unmatched_b[c]
                sim = 1.0 - cost_matrix[r, c]

                if sim >= self.threshold:
                    matched_a_indices.add(idx_a)
                    matched_b_indices.add(idx_b)
                    diff_entry = self._build_pair_diff(clauses_a[idx_a], clauses_b[idx_b], idx_a, idx_b, similarity=sim)
                    aligned_results.append(diff_entry)

        # Step 3: Unmatched clauses from Document A -> REMOVED
        for idx_a, ca in enumerate(clauses_a):
            if idx_a not in matched_a_indices:
                aligned_results.append(
                    {
                        "status": "removed",
                        "clause_a": ca,
                        "clause_b": None,
                        "similarity": 0.0,
                        "diff_tokens": [{"type": "delete", "text": ca.get("text", "")}],
                        "relative_shift": None,
                    }
                )

        # Step 4: Unmatched clauses from Document B -> ADDED
        for idx_b, cb in enumerate(clauses_b):
            if idx_b not in matched_b_indices:
                aligned_results.append(
                    {
                        "status": "added",
                        "clause_a": None,
                        "clause_b": cb,
                        "similarity": 0.0,
                        "diff_tokens": [{"type": "insert", "text": cb.get("text", "")}],
                        "relative_shift": None,
                    }
                )

        # Step 5: Sort aligned results logically (by index in A or index in B)
        def sort_key(item):
            ca = item.get("clause_a")
            cb = item.get("clause_b")
            idx_a = ca.get("clause_index", 9999) if ca else 9999
            idx_b = cb.get("clause_index", 9999) if cb else 9999
            return (min(idx_a, idx_b), idx_a, idx_b)

        aligned_results.sort(key=sort_key)
        return aligned_results

    def _build_pair_diff(
        self,
        clause_a: Dict[str, Any],
        clause_b: Dict[str, Any],
        idx_a: int,
        idx_b: int,
        similarity: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Classifies pair into unchanged, modified, or moved and generates redline tokens."""
        text_a = clause_a.get("text", "").strip()
        text_b = clause_b.get("text", "").strip()

        if similarity is None:
            emb_a = clause_a.get("embedding")
            emb_b = clause_b.get("embedding")
            similarity = compute_cosine_similarity(emb_a, emb_b)

        relative_shift = abs(idx_a - idx_b)

        if text_a == text_b:
            if relative_shift >= 2:
                status = "moved"
            else:
                status = "unchanged"
            diff_tokens = [{"type": "equal", "text": text_a}]
        else:
            if relative_shift >= 3 and similarity >= 0.85:
                status = "moved"
            else:
                status = "modified"
            diff_tokens = compute_word_diff(text_a, text_b)

        return {
            "status": status,
            "clause_a": clause_a,
            "clause_b": clause_b,
            "similarity": round(float(similarity), 4),
            "diff_tokens": diff_tokens,
            "relative_shift": relative_shift,
        }
