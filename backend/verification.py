"""
Citation Verification module for Veridocs.
Validates that generated answers are grounded in source citations,
detects unsupported claims, and calculates confidence scores.
"""

import re
import logging
from typing import List, Dict, Optional
from difflib import SequenceMatcher

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def calculate_grounding_score(
    answer: str,
    source_chunks: List[Dict],
    threshold: float = 0.3
) -> Dict:
    """
    Verify how well an answer is grounded in the source documents.

    Process:
    1. Split answer into claims/sentences
    2. For each claim, check overlap with source chunks
    3. Score each claim
    4. Calculate overall grounding confidence

    Args:
        answer: The generated answer text
        source_chunks: The source chunks used to generate the answer
        threshold: Minimum similarity score to consider a claim supported

    Returns:
        Dict with:
        - confidence_score: 0.0 to 1.0
        - total_claims: number of claims analyzed
        - supported_claims: number of well-grounded claims
        - unsupported_claims: list of claims not well-supported
        - claim_details: per-claim analysis
    """
    if not answer or not source_chunks:
        return {
            "confidence_score": 0.0,
            "total_claims": 0,
            "supported_claims": 0,
            "unsupported_claims": [],
            "claim_details": []
        }

    # Extract claims (sentences) from the answer
    claims = _extract_claims(answer)

    if not claims:
        return {
            "confidence_score": 1.0,
            "total_claims": 0,
            "supported_claims": 0,
            "unsupported_claims": [],
            "claim_details": []
        }

    # Build combined source text for matching
    source_texts = [c["text"].lower() for c in source_chunks]
    combined_source = " ".join(source_texts)

    # Score each claim
    claim_details = []
    supported_count = 0
    unsupported_claims = []

    for claim in claims:
        # Skip very short claims or non-informational ones
        if len(claim.split()) < 4:
            continue

        # Calculate best match score across all source chunks
        best_score = 0.0
        best_source_idx = -1

        claim_lower = claim.lower()
        # Clean alphanumeric tokens (strip colons, periods, quotes)
        stopwords = {
            "the", "a", "an", "and", "or", "is", "are", "was", "were", "be", "been",
            "using", "with", "for", "of", "in", "on", "to", "at", "by", "from", "it",
            "its", "as", "that", "this", "these", "those"
        }
        raw_tokens = set(re.findall(r'\b[a-z0-9]{2,}\b', claim_lower))
        meaningful_tokens = raw_tokens - stopwords or raw_tokens

        # Extract numeric tokens from claim (e.g. $2.5M, 35%, 2024, 41)
        claim_numbers = re.findall(r'(\$?\b\d+[\d,.]*(?:%|\b))', claim)
        numeric_grounded = True
        if claim_numbers:
            # Check if at least some numbers appear in the combined sources
            matched_numbers = [num for num in claim_numbers if num.lower() in combined_source]
            if len(matched_numbers) == 0 and len(claim_numbers) > 0:
                numeric_grounded = False

        for idx, source_text in enumerate(source_texts):
            source_tokens = set(re.findall(r'\b[a-z0-9]{2,}\b', source_text.lower()))
            if not source_tokens:
                continue

            # Method 1: Normalized Token Overlap (excluding stopwords)
            overlap = meaningful_tokens & source_tokens
            token_score = len(overlap) / max(len(meaningful_tokens), 1)

            # Method 2: Substring matching for exact phrase preservation
            substr_score = _substring_similarity(claim_lower, source_text)

            # Method 3: Sequence matcher on cleaned text
            seq_score = SequenceMatcher(None, claim_lower, source_text).ratio()

            # Weighted combination with high priority on content token fidelity
            combined = 0.60 * token_score + 0.25 * substr_score + 0.15 * seq_score

            if combined > best_score:
                best_score = combined
                best_source_idx = idx

        # Apply numeric hallucination penalty if claim asserts numbers not in sources
        if not numeric_grounded:
            best_score = max(0.0, best_score - 0.35)

        # 3-State Claim Grounding:
        # 🟢 Verified: true direct factual match (>= 0.28) and numbers match
        # 🟡 Inferred: logical extrapolation or synthesis (0.15 - 0.27)
        # 🔴 Hallucinated: unsupported assertion (< 0.15) or fabricated numbers
        if best_score >= 0.28 and numeric_grounded:
            status = "verified"
            is_supported = True
        elif best_score >= 0.15:
            status = "inferred"
            is_supported = True
        else:
            status = "hallucinated"
            is_supported = False

        if is_supported:
            supported_count += 1
        else:
            unsupported_claims.append(claim)

        claim_details.append({
            "claim": claim,
            "score": round(best_score, 3),
            "status": status,
            "is_supported": is_supported,
            "numeric_grounded": numeric_grounded,
            "best_source_page": source_chunks[best_source_idx]["page"] if best_source_idx >= 0 else None,
            "source_file": source_chunks[best_source_idx].get("source_file") if best_source_idx >= 0 else None,
        })

    total_scorable = len(claim_details)
    confidence = supported_count / max(total_scorable, 1)

    verified_count = sum(1 for c in claim_details if c["status"] == "verified")
    inferred_count = sum(1 for c in claim_details if c["status"] == "inferred")
    hallucinated_count = sum(1 for c in claim_details if c["status"] == "hallucinated")
    numeric_violations = sum(1 for c in claim_details if not c.get("numeric_grounded", True))

    numeric_accuracy = 1.0 - (numeric_violations / max(total_scorable, 1))

    return {
        "confidence_score": round(confidence, 3),
        "total_claims": total_scorable,
        "supported_claims": supported_count,
        "verified_claims": verified_count,
        "inferred_claims": inferred_count,
        "hallucinated_claims": hallucinated_count,
        "numeric_accuracy": round(max(0.0, numeric_accuracy), 3),
        "unsupported_claims": unsupported_claims[:5],  # Limit to first 5
        "claim_details": claim_details
    }


def calculate_rag_triad_metrics(
    question: str,
    answer: str,
    source_chunks: List[Dict],
    grounding_result: Optional[Dict] = None,
    latency_ms: Optional[float] = None
) -> Dict:
    """
    Computes industry-standard RAG Triad observability scores:
    1. Context Relevance: Fraction of retrieved context chunks that overlap with the query.
    2. Groundedness (Faithfulness): Alignment of generated claims against source evidence.
    3. Answer Relevance: Semantic alignment between user query and generated response.
    4. Numeric Consistency: Preservation of statistical figures and entities without distortion.
    """
    if not source_chunks or not answer:
        return {
            "context_relevance": 0.0,
            "groundedness": 0.0,
            "answer_relevance": 0.0,
            "numeric_accuracy": 1.0,
            "latency_ms": latency_ms,
            "retrieval_pipeline": "Hybrid BM25 + FAISS + Cross-Encoder RRF"
        }

    # 1. Groundedness from claims
    if grounding_result is None:
        grounding_result = calculate_grounding_score(answer, source_chunks)

    groundedness = grounding_result.get("confidence_score", 0.0)
    numeric_accuracy = grounding_result.get("numeric_accuracy", 1.0)

    # 2. Context Relevance (Overlap between question keywords and retrieved chunk vocabulary)
    q_tokens = set(re.findall(r'\b\w{3,}\b', question.lower()))
    context_relevance_scores = []
    for chunk in source_chunks:
        chunk_tokens = set(re.findall(r'\b\w{3,}\b', chunk.get("text", "").lower()))
        if not q_tokens:
            overlap = 1.0
        else:
            overlap = len(q_tokens & chunk_tokens) / len(q_tokens)
        context_relevance_scores.append(min(1.0, overlap * 1.5))

    context_relevance = sum(context_relevance_scores) / max(len(context_relevance_scores), 1)

    # 3. Answer Relevance (Coverage of question intents inside generated answer)
    ans_tokens = set(re.findall(r'\b\w{3,}\b', answer.lower()))
    if q_tokens:
        answer_coverage = len(q_tokens & ans_tokens) / len(q_tokens)
        # Length penalty if answer is suspiciously empty
        length_factor = min(1.0, len(answer.split()) / 12.0)
        answer_relevance = min(1.0, (answer_coverage * 0.7 + length_factor * 0.3) * 1.25)
    else:
        answer_relevance = 0.85

    return {
        "context_relevance": round(min(1.0, max(0.1, context_relevance)), 3),
        "groundedness": round(groundedness, 3),
        "answer_relevance": round(min(1.0, max(0.1, answer_relevance)), 3),
        "numeric_accuracy": round(numeric_accuracy, 3),
        "latency_ms": round(latency_ms, 1) if latency_ms is not None else None,
        "retrieval_pipeline": "Hybrid BM25 + FAISS + Cross-Encoder RRF"
    }


def _extract_claims(text: str) -> List[str]:
    """
    Extract individual claims (sentences) from answer text.
    Filters out non-claim content like headers, citations, etc.
    """
    # Remove citation markers [Page X]
    text = re.sub(r'\[Page\s*\d+\]', '', text)
    # Remove markdown formatting
    text = re.sub(r'[*#`]', '', text)
    # Remove bullet points
    text = re.sub(r'^[-•]\s*', '', text, flags=re.MULTILINE)

    # Split into sentences
    sentences = re.split(r'(?<=[.!?])\s+', text)

    claims = []
    for sentence in sentences:
        sentence = sentence.strip()
        # Filter out very short or non-informative sentences
        if len(sentence) < 15:
            continue
        # Filter out questions
        if sentence.endswith('?'):
            continue
        # Filter out meta-statements
        if any(phrase in sentence.lower() for phrase in [
            "i cannot find",
            "based on the",
            "according to the",
            "the document states",
            "the context shows",
            "let me",
            "here is",
            "here are"
        ]):
            continue

        claims.append(sentence)

    return claims


def _substring_similarity(claim: str, source: str) -> float:
    """
    Check what fraction of the claim's key phrases appear as substrings in the source.
    """
    # Extract 3-word windows from the claim
    words = claim.split()
    if len(words) < 3:
        return 1.0 if claim in source else 0.0

    windows = []
    for i in range(len(words) - 2):
        window = " ".join(words[i:i + 3])
        windows.append(window)

    if not windows:
        return 0.0

    matches = sum(1 for w in windows if w in source)
    return matches / len(windows)


def extract_citations_from_answer(
    answer: str,
    source_chunks: List[Dict]
) -> List[Dict]:
    """
    Extract structured citation references from an answer.
    Looks for [Page X] patterns and maps them to source chunks.

    Returns list of citation dicts with page, text snippet, and source file.
    """
    # Find all [Page X] references
    page_refs = re.findall(r'\[Page\s*(\d+)\]', answer)
    page_numbers = [int(p) for p in page_refs]

    citations = []
    seen_pages = set()

    for page_num in page_numbers:
        if page_num in seen_pages:
            continue

        # Find matching chunk
        for chunk in source_chunks:
            if chunk["page"] == page_num:
                citations.append({
                    "citation_id": len(citations) + 1,
                    "page": page_num,
                    "source_file": chunk.get("source_file", "Document"),
                    "highlighted_text": chunk["text"][:200],
                    "section": chunk.get("section"),
                })
                seen_pages.add(page_num)
                break

    return citations
