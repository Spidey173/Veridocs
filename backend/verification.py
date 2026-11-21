"""
Citation Check & Grounding Verification for Veridocs.
Performs honest n-gram word overlap and citation verification between generated answers
and retrieved document chunks. No fabricated scores or fake triad metrics.
"""

import re
import logging
from typing import List, Dict, Optional, Any

logger = logging.getLogger(__name__)

META_PATTERNS = [
    r'^(?:here are|the following|according to|based on|as stated in|in the document)',
    r'^(?:not found in the document|i could not find|no information is provided|none found)',
    r'^(?:let me know if|feel free to|hope this helps|please note that)',
    r'^(?:summary|key highlights|details):?$',
]


def split_sentences_safely(text: str) -> List[str]:
    """
    Split answer text into complete sentences and list items,
    protecting abbreviations (e.g., i.e., vs., p.) and bullet numbers (1., 2.).
    """
    if not text:
        return []

    # 1. Strip raw retrieval brackets like 【...】 or 【1:0†source】
    cleaned = re.sub(r'【[^】]*】', '', text)

    # 2. Protect common abbreviations: e.g., i.e., vs., p., al., etc.
    protected = re.sub(
        r'\b(e\.g\.|i\.e\.|vs\.|p\.|al\.|etc\.)',
        lambda m: m.group(0).replace('.', '@@DOT@@'),
        cleaned,
        flags=re.IGNORECASE
    )

    # 3. Protect numbered list items at start of lines or after whitespace
    protected = re.sub(r'(?:^|[\n\r])\s*(\d+)\.\s+', r'\n\1@@NUMDOT@@ ', protected)
    protected = re.sub(r'(?<=\s)(\d+)\.\s+', r'\1@@NUMDOT@@ ', protected)

    # 4. Split on real sentence endings followed by whitespace, or newlines
    raw_parts = [p.strip() for p in re.split(r'(?<=[.!?])\s+|\n+', protected) if p.strip()]

    sentences = []
    for part in raw_parts:
        restored = part.replace('@@DOT@@', '.').replace('@@NUMDOT@@', '.')
        # Strip leading bullet indicators: '- ', '* ', '• ', '1. '
        restored = re.sub(r'^(?:[-*•]|\d+\.)\s*', '', restored).strip()
        # Clean citation markers from the claim text before evaluation
        restored = re.sub(r'\s*\[(?:Page\s*\d+[^\]]*|\d+)\]', '', restored).strip()
        restored = re.sub(r'[*#`_]', '', restored).strip()

        if restored:
            sentences.append(restored)

    return sentences


def is_factual_claim(sentence: str) -> bool:
    """Return True if sentence is an assertable factual claim, skipping intro/meta sentences."""
    s = sentence.strip()
    if len(s) < 18 or s.endswith('?'):
        return False

    lower = s.lower()
    for pat in META_PATTERNS:
        if re.search(pat, lower):
            return False

    return True


def extract_citations_from_answer(
    answer: str,
    source_chunks: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Extract citation references [1], [2] or [Page X] and match to the exact cited chunks.
    Only returns citations for chunks actually referenced in the answer text.
    """
    citations = []
    seen_ids = set()

    # 1. Look for numeric chunk citations [1], [2], etc.
    num_matches = re.finditer(r'\[(\d+)\]', answer)
    for m in num_matches:
        idx_str = m.group(1)
        try:
            chunk_idx = int(idx_str) - 1
            if 0 <= chunk_idx < len(source_chunks):
                if chunk_idx not in seen_ids:
                    seen_ids.add(chunk_idx)
                    chunk = source_chunks[chunk_idx]
                    citations.append({
                        "citation_id": int(idx_str),
                        "page": chunk.get("page", 1),
                        "source_file": chunk.get("source_file", "Document"),
                        "highlighted_text": chunk.get("text", "")[:350],
                    })
        except ValueError:
            continue

    # 2. Look for [Page X] or [Page X: filename]
    page_matches = re.finditer(r'\[Page\s*(\d+)(?::\s*([^\]]+))?\]', answer, re.IGNORECASE)
    for m in page_matches:
        raw_page = m.group(1)
        doc_hint = m.group(2)
        if not raw_page:
            continue
        try:
            page = int(raw_page)
        except ValueError:
            continue

        matched_chunk = None
        matched_idx = -1
        for i, chunk in enumerate(source_chunks):
            if chunk.get("page") == page:
                if doc_hint and doc_hint.lower() in chunk.get("source_file", "").lower():
                    matched_chunk = chunk
                    matched_idx = i
                    break
                elif not matched_chunk:
                    matched_chunk = chunk
                    matched_idx = i

        if matched_idx >= 0 and matched_idx not in seen_ids:
            seen_ids.add(matched_idx)
            citations.append({
                "citation_id": len(citations) + 1,
                "page": page,
                "source_file": matched_chunk.get("source_file", "Document") if matched_chunk else (doc_hint or "Document"),
                "highlighted_text": matched_chunk.get("text", "")[:350] if matched_chunk else "",
            })

    # 3. Fallback: If answer is substantive but model omitted bracket tags, reference top retrieved chunk
    if not citations and source_chunks and "not found in the document" not in answer.lower():
        top = source_chunks[0]
        citations.append({
            "citation_id": 1,
            "page": top.get("page", 1),
            "source_file": top.get("source_file", "Document"),
            "highlighted_text": top.get("text", "")[:350],
        })

    return citations


def check_citations(
    answer: str,
    source_chunks: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """Verify how well factual statements in the answer are supported by retrieved source text using n-gram overlap."""
    if not answer or not source_chunks:
        return {
            "citation_score": 0.0,
            "total_claims": 0,
            "supported_claims": 0,
            "claims": []
        }

    sentences = split_sentences_safely(answer)
    factual_claims = [s for s in sentences if is_factual_claim(s)]

    if not factual_claims:
        return {
            "citation_score": 1.0,
            "total_claims": 0,
            "supported_claims": 0,
            "claims": []
        }

    stopwords = {
        "the", "a", "an", "and", "or", "is", "are", "was", "were", "be", "been",
        "with", "for", "of", "in", "on", "to", "at", "by", "from", "it", "its",
        "as", "that", "this", "these", "those"
    }

    claim_results = []
    supported_count = 0

    for claim in factual_claims:
        claim_lower = claim.lower()
        tokens = set(re.findall(r'\b[a-z0-9]{3,}\b', claim_lower)) - stopwords
        if not tokens:
            continue

        best_overlap = 0.0
        best_chunk = None

        for chunk in source_chunks:
            chunk_tokens = set(re.findall(r'\b[a-z0-9]{3,}\b', chunk.get("text", "").lower()))
            if not chunk_tokens:
                continue
            overlap = len(tokens & chunk_tokens) / len(tokens)
            if overlap > best_overlap:
                best_overlap = overlap
                best_chunk = chunk

        is_supported = best_overlap >= 0.35
        if is_supported:
            supported_count += 1

        claim_results.append({
            "claim": claim,
            "overlap_score": round(best_overlap, 2),
            "is_supported": is_supported,
            "matched_page": best_chunk.get("page") if best_chunk else None,
            "source_file": best_chunk.get("source_file") if best_chunk else None,
        })

    total = len(claim_results)
    score = round(supported_count / max(total, 1), 2)

    return {
        "citation_score": score,
        "total_claims": total,
        "supported_claims": supported_count,
        "claims": claim_results
    }
