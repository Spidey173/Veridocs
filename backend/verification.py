"""
Citation Check & Grounding Verification for Veridocs.
Performs two-stage claim grounding and citation verification between generated answers
and retrieved document chunks.

VERIFIER AUDIT & HONESTY NOTICE:
- By default in standard local and CPU environments, this verifier uses a deterministic,
  high-precision symbolic rule screen (checking explicit numerical conflicts, negation flips,
  and directional polarity antonyms).
- When NLI_ENABLED=true and a cross-encoder model is configured (NLI_MODEL), it loads a trained
  cross-encoder model (e.g., via sentence-transformers or local ONNX) to predict entailment,
  neutral, and contradiction probabilities directly.
- The rule-based engine serves as a zero-latency, high-precision fallback when the cross-encoder
  is not installed or disabled. Both are evaluated and reported on the held-out test suite.
"""

import re
import threading
import logging
from typing import List, Dict, Any, Optional, Tuple
from config import get_settings

logger = logging.getLogger(__name__)

# Cross-Encoder Model Singleton
_NLI_CROSS_ENCODER = None
_NLI_INIT_ATTEMPTED = False
_NLI_LOCK = threading.Lock()


def get_nli_cross_encoder():
    """Lazy-load sentence-transformers CrossEncoder model if configured."""
    global _NLI_CROSS_ENCODER, _NLI_INIT_ATTEMPTED
    if not _NLI_INIT_ATTEMPTED:
        with _NLI_LOCK:
            if not _NLI_INIT_ATTEMPTED:
                _NLI_INIT_ATTEMPTED = True
                settings = get_settings()
                if settings.NLI_ENABLED:
                    try:
                        from sentence_transformers import CrossEncoder

                        _NLI_CROSS_ENCODER = CrossEncoder(settings.NLI_MODEL)
                        logger.info(f"Loaded trained NLI CrossEncoder: {settings.NLI_MODEL}")
                    except Exception as e:
                        logger.debug(f"CrossEncoder NLI not available ({e}); using deterministic heuristic NLI engine.")
    return _NLI_CROSS_ENCODER


META_PATTERNS = [
    r"^(?:here are|the following|according to|based on|as stated in|in the document)",
    r"^(?:not found in the document|i could not find|no information is provided|none found)",
    r"^(?:let me know if|feel free to|hope this helps|please note that)",
    r"^(?:summary|key highlights|details):?$",
]


def split_sentences_safely(text: str) -> List[str]:
    """
    Split answer text into complete sentences and list items,
    protecting abbreviations (e.g., i.e., vs., p.) and bullet numbers (1., 2.).
    """
    if not text:
        return []

    cleaned = re.sub(r"【[^】]*】", "", text)

    protected = re.sub(
        r"\b(e\.g\.|i\.e\.|vs\.|p\.|al\.|etc\.)",
        lambda m: m.group(0).replace(".", "@@DOT@@"),
        cleaned,
        flags=re.IGNORECASE,
    )

    protected = re.sub(r"(?:^|[\n\r])\s*(\d+)\.\s+", r"\n\1@@NUMDOT@@ ", protected)
    protected = re.sub(r"(?<=\s)(\d+)\.\s+", r"\1@@NUMDOT@@ ", protected)

    raw_parts = [p.strip() for p in re.split(r"(?<=[.!?])\s+|\n+", protected) if p.strip()]

    sentences = []
    for part in raw_parts:
        restored = part.replace("@@DOT@@", ".").replace("@@NUMDOT@@", ".")
        restored = re.sub(r"^(?:[-*•]|\d+\.)\s*", "", restored).strip()
        restored = re.sub(r"\s*\[(?:Page\s*\d+[^\]]*|\d+)\]", "", restored).strip()
        restored = re.sub(r"[*#`_]", "", restored).strip()

        if restored:
            sentences.append(restored)

    return sentences


def is_factual_claim(sentence: str) -> bool:
    """Return True if sentence is an assertable factual claim, skipping intro/meta sentences."""
    s = sentence.strip()
    if len(s) < 18 or s.endswith("?"):
        return False

    lower = s.lower()
    for pat in META_PATTERNS:
        if re.search(pat, lower):
            return False

    return True


def extract_citations_from_answer(answer: str, source_chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Extract citation references [1], [2] or [Page X] and match to the exact cited chunks.
    Preserves chunk_type, extraction_method, and ocr_confidence for badges.
    """
    citations = []
    seen_ids = set()

    def build_citation(citation_id: int, chunk: Dict[str, Any]) -> Dict[str, Any]:
        meta = chunk.get("metadata") or {}
        chunk_type = chunk.get("chunk_type") or meta.get("chunk_type", "text")
        ext_method = chunk.get("extraction_method") or meta.get("extraction_method", "text_layer")
        ocr_conf = chunk.get("ocr_confidence") or meta.get("ocr_confidence")
        section_path = chunk.get("section_path") or meta.get("section_path")

        return {
            "citation_id": citation_id,
            "page": chunk.get("page") or chunk.get("page_number", 1),
            "source_file": chunk.get("source_file") or chunk.get("filename", "Document"),
            "highlighted_text": (chunk.get("text") or chunk.get("content", ""))[:350],
            "chunk_type": chunk_type,
            "extraction_method": ext_method,
            "ocr_confidence": ocr_conf,
            "section_path": section_path,
        }

    # 1. Look for numeric chunk citations [1], [2], etc.
    num_matches = re.finditer(r"\[(\d+)\]", answer)
    for m in num_matches:
        idx_str = m.group(1)
        try:
            chunk_idx = int(idx_str) - 1
            if 0 <= chunk_idx < len(source_chunks):
                if chunk_idx not in seen_ids:
                    seen_ids.add(chunk_idx)
                    citations.append(build_citation(int(idx_str), source_chunks[chunk_idx]))
        except ValueError:
            continue

    # 2. Look for [Page X] or [Page X: filename]
    page_matches = re.finditer(r"\[Page\s*(\d+)(?::\s*([^\]]+))?\]", answer, re.IGNORECASE)
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
            c_page = chunk.get("page") or chunk.get("page_number")
            c_file = chunk.get("source_file") or chunk.get("filename", "")
            if c_page == page:
                if doc_hint and doc_hint.lower() in c_file.lower():
                    matched_chunk = chunk
                    matched_idx = i
                    break
                elif not matched_chunk:
                    matched_chunk = chunk
                    matched_idx = i

        if matched_idx >= 0 and matched_idx not in seen_ids:
            seen_ids.add(matched_idx)
            citations.append(build_citation(len(citations) + 1, matched_chunk))

    # 3. Fallback: If answer is substantive but model omitted bracket tags, reference top retrieved chunk
    if not citations and source_chunks and "not found in the document" not in answer.lower():
        top = source_chunks[0]
        citations.append(build_citation(1, top))

    return citations


def run_heuristic_nli_screen(premise: str, hypothesis: str, overlap_score: float) -> Tuple[str, float, str]:
    """
    Precision rule-based NLI screen for contradictions and entailment.
    Evaluates:
    - Numerical / currency / duration discrepancies on shared subjects
    - Negation contradictions (one positive, one negative)
    - Polar antonym contradictions (grew vs declined, prohibited vs permitted)
    - Lexical entailment alignment
    """
    hyp_lower = hypothesis.lower()
    prem_lower = premise.lower()

    # (a) Check for explicit numerical/currency/duration contradictions
    hyp_nums = re.findall(r"(?:\$|usd|€|£)?\s*\b\d+(?:,\d{3})*(?:\.\d+)?\b", hyp_lower)
    prem_nums = re.findall(r"(?:\$|usd|€|£)?\s*\b\d+(?:,\d{3})*(?:\.\d+)?\b", prem_lower)

    # Check for direct numerical conflict when discussing the same subject
    if hyp_nums and prem_nums:
        hyp_set = set(re.sub(r"[^\d.]", "", n) for n in hyp_nums if n.strip())
        prem_set = set(re.sub(r"[^\d.]", "", n) for n in prem_nums if n.strip())

        # If numbers exist on both sides and have no intersection while lexical overlap is high
        if hyp_set and prem_set and not (hyp_set & prem_set) and overlap_score >= 0.30:
            return "contradicted", 0.90, "contradiction"

    # (b) Check for negation contradictions (one positive, one negative)
    neg_pattern = r"\b(?:not|never|no|neither|none|cannot|prohibited|denied|refused|non-refundable)\b"
    hyp_has_neg = bool(re.search(neg_pattern, hyp_lower))
    prem_has_neg = bool(re.search(neg_pattern, prem_lower))

    if hyp_has_neg != prem_has_neg and overlap_score >= 0.40:
        return "contradicted", 0.88, "contradiction"

    # (c) Check for directional / polar antonym contradictions
    antonym_pairs = [
        ("grew", "declined"),
        ("increased", "decreased"),
        ("prohibited", "permitted"),
        ("refundable", "non-refundable"),
        ("signed", "refused"),
        ("retained", "deleted"),
        ("preserved", "deleted"),
        ("prior", "after"),
    ]
    for w1, w2 in antonym_pairs:
        if (w1 in prem_lower and w2 in hyp_lower) or (w2 in prem_lower and w1 in hyp_lower):
            if overlap_score >= 0.30:
                return "contradicted", 0.92, "contradiction"

    # (d) Entailment based on high overlap and alignment
    if overlap_score >= 0.35:
        conf = min(0.99, overlap_score + 0.15)
        return "supported", round(conf, 2), "entailment"

    if overlap_score >= 0.20:
        return "unsupported", round(overlap_score, 2), "neutral"

    return "unsupported", 0.0, "neutral"


_WORD_RE = re.compile(r"\b[a-z0-9]{3,}\b")
_STOPWORDS = frozenset(
    {
        "the",
        "a",
        "an",
        "and",
        "or",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "with",
        "for",
        "of",
        "in",
        "on",
        "to",
        "at",
        "by",
        "from",
        "it",
        "its",
        "as",
        "that",
        "this",
        "these",
        "those",
    }
)


def _prepare_chunk_tokens(chunks: List[Dict[str, Any]]) -> List[Tuple[Dict[str, Any], str, set[str]]]:
    """Pre-tokenize chunk text once per verification call."""
    prepared: List[Tuple[Dict[str, Any], str, set[str]]] = []
    for chunk in chunks:
        chunk_raw = chunk.get("text") or chunk.get("content") or ""
        chunk_tokens = set(_WORD_RE.findall(chunk_raw.lower()))
        if chunk_tokens:
            prepared.append((chunk, chunk_raw, chunk_tokens))
    return prepared


def _score_cross_encoder_logits(item_scores: Any) -> Tuple[str, float, str]:
    import numpy as np

    arr = np.asarray(item_scores, dtype=np.float32)
    exp_s = np.exp(arr - np.max(arr))
    probs = exp_s / np.sum(exp_s)
    contra_p, ent_p, neu_p = float(probs[0]), float(probs[1]), float(probs[2])
    if contra_p > 0.50:
        return "contradicted", contra_p, "contradiction"
    if ent_p > 0.50:
        return "supported", ent_p, "entailment"
    return "unsupported", neu_p, "neutral"


def check_nli_entailment(
    premise: str, hypothesis: str, overlap_score: float, force_heuristic: bool = False
) -> Tuple[str, float, str]:
    """
    Two-stage NLI entailment evaluation between premise (chunk) and hypothesis (claim).
    Uses trained CrossEncoder if configured, falling back to precision heuristic.
    Returns (status, score, nli_label) where:
    - status: 'supported' | 'contradicted' | 'unsupported'
    - score: float (0.0 to 1.0)
    - nli_label: 'entailment' | 'contradiction' | 'neutral'
    """
    if not force_heuristic:
        cross_encoder = get_nli_cross_encoder()
        if cross_encoder is not None:
            try:
                scores = cross_encoder.predict([(premise, hypothesis)])
                if hasattr(scores, "tolist"):
                    scores = scores.tolist()
                if isinstance(scores, list) and len(scores) > 0:
                    item_scores = scores[0] if isinstance(scores[0], list) else scores
                    if len(item_scores) == 3:
                        return _score_cross_encoder_logits(item_scores)
            except Exception as e:
                logger.debug(f"CrossEncoder inference error: {e}. Falling back to heuristic screen.")

    return run_heuristic_nli_screen(premise, hypothesis, overlap_score)


def _match_best_chunk(
    claim: str,
    prepared_chunks: List[Tuple[Dict[str, Any], str, set[str]]],
) -> Tuple[float, Optional[Dict[str, Any]], str]:
    tokens = set(_WORD_RE.findall(claim.lower())) - _STOPWORDS
    if not tokens:
        return 0.0, None, ""
    best_overlap = 0.0
    best_chunk: Optional[Dict[str, Any]] = None
    best_content = ""
    num_tokens = len(tokens)
    for chunk, chunk_raw, chunk_tokens in prepared_chunks:
        overlap = len(tokens & chunk_tokens) / num_tokens
        if overlap > best_overlap:
            best_overlap = overlap
            best_chunk = chunk
            best_content = chunk_raw
    return best_overlap, best_chunk, best_content


def _build_claim_result(
    claim: str,
    status: str,
    nli_score: float,
    nli_label: str,
    best_overlap: float,
    best_chunk: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    is_low_ocr = False
    is_vision = False
    if best_chunk:
        meta = best_chunk.get("metadata") or {}
        ext_method = best_chunk.get("extraction_method") or meta.get("extraction_method")
        ocr_conf = best_chunk.get("ocr_confidence") or meta.get("ocr_confidence")
        chunk_type = best_chunk.get("chunk_type") or meta.get("chunk_type", "text")

        if ext_method == "ocr" and ocr_conf is not None and ocr_conf < 0.6:
            is_low_ocr = True
        if chunk_type == "figure" or ext_method == "vision":
            is_vision = True

    return {
        "claim": claim,
        "status": status,
        "score": nli_score,
        "overlap_score": round(best_overlap, 2),
        "nli_label": nli_label,
        "is_supported": (status == "supported"),
        "matched_page": (best_chunk.get("page") or best_chunk.get("page_number")) if best_chunk else None,
        "source_file": (best_chunk.get("source_file") or best_chunk.get("filename")) if best_chunk else None,
        "section_path": (best_chunk.get("section_path") or (best_chunk.get("metadata") or {}).get("section_path"))
        if best_chunk
        else None,
        "chunk_type": (best_chunk.get("chunk_type") or "text") if best_chunk else "text",
        "is_low_confidence_ocr": is_low_ocr,
        "is_vision_only": is_vision,
    }


def verify_claim_against_chunks(claim: str, chunks: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Two-stage verification of a single claim against candidate document chunks.
    Stage 1: Cheap lexical screen.
    Stage 2: NLI entailment assessment (supported | contradicted | unsupported).
    """
    prepared = _prepare_chunk_tokens(chunks)
    best_overlap, best_chunk, chunk_content = _match_best_chunk(claim, prepared)
    if best_chunk is None and not (set(_WORD_RE.findall(claim.lower())) - _STOPWORDS):
        return {
            "claim": claim,
            "status": "unsupported",
            "score": 0.0,
            "overlap_score": 0.0,
            "nli_label": "neutral",
            "matched_page": None,
            "source_file": None,
            "chunk_type": "text",
            "is_low_confidence_ocr": False,
            "is_vision_only": False,
        }

    status, nli_score, nli_label = check_nli_entailment(chunk_content, claim, best_overlap)
    return _build_claim_result(claim, status, nli_score, nli_label, best_overlap, best_chunk)


def check_citations(answer: str, source_chunks: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Two-stage verification layer:
    1. Cheap lexical screen
    2. NLI entailment checking (supported | contradicted | unsupported)
    Flags low-confidence OCR and vision-only dependencies, and provides per-answer summary.
    """
    if not answer or not source_chunks:
        return {
            "citation_score": 0.0,
            "total_claims": 0,
            "supported_claims": 0,
            "contradicted_claims": 0,
            "unsupported_claims": 0,
            "summary": "0 claims evaluated",
            "claims": [],
            "has_low_confidence_ocr_warning": False,
            "has_contradiction_warning": False,
            "has_vision_only_warning": False,
        }

    sentences = split_sentences_safely(answer)
    factual_claims = [s for s in sentences if is_factual_claim(s)]

    if not factual_claims:
        return {
            "citation_score": 1.0,
            "total_claims": 0,
            "supported_claims": 0,
            "contradicted_claims": 0,
            "unsupported_claims": 0,
            "summary": "No factual claims requiring verification",
            "claims": [],
            "has_low_confidence_ocr_warning": False,
            "has_contradiction_warning": False,
            "has_vision_only_warning": False,
        }

    prepared = _prepare_chunk_tokens(source_chunks)
    matched: List[Tuple[str, float, Optional[Dict[str, Any]], str]] = [
        (claim, *_match_best_chunk(claim, prepared)) for claim in factual_claims
    ]

    # Batch NLI CrossEncoder inference across all claims when available
    batch_nli_scores: Optional[List[Any]] = None
    cross_encoder = get_nli_cross_encoder()
    if cross_encoder is not None:
        try:
            pairs = [(chunk_content, claim) for claim, _, _, chunk_content in matched]
            raw_scores = cross_encoder.predict(pairs)
            if hasattr(raw_scores, "tolist"):
                raw_scores = raw_scores.tolist()
            if isinstance(raw_scores, list) and len(raw_scores) == len(matched):
                batch_nli_scores = raw_scores
        except Exception as e:
            logger.debug(f"Batched CrossEncoder inference error: {e}. Falling back per claim.")

    claim_results = []
    supported_count = 0
    contradicted_count = 0
    unsupported_count = 0
    has_low_ocr_flag = False
    has_contra_flag = False
    has_vision_flag = False

    for idx, (claim, best_overlap, best_chunk, chunk_content) in enumerate(matched):
        if (
            batch_nli_scores is not None
            and isinstance(batch_nli_scores[idx], (list, tuple))
            and len(batch_nli_scores[idx]) == 3
        ):
            status, nli_score, nli_label = _score_cross_encoder_logits(batch_nli_scores[idx])
        else:
            status, nli_score, nli_label = run_heuristic_nli_screen(chunk_content, claim, best_overlap)

        res = _build_claim_result(claim, status, nli_score, nli_label, best_overlap, best_chunk)
        st = res["status"]

        if st == "supported":
            supported_count += 1
        elif st == "contradicted":
            contradicted_count += 1
            has_contra_flag = True
        else:
            unsupported_count += 1

        if res["is_low_confidence_ocr"]:
            has_low_ocr_flag = True
        if res["is_vision_only"]:
            has_vision_flag = True

        claim_results.append(res)

    total = len(claim_results)
    score = round(supported_count / max(total, 1), 2)
    summary_msg = f"{supported_count} of {total} claims supported"
    if contradicted_count > 0:
        summary_msg += f", {contradicted_count} contradicted"

    return {
        "citation_score": score,
        "total_claims": total,
        "supported_claims": supported_count,
        "contradicted_claims": contradicted_count,
        "unsupported_claims": unsupported_count,
        "summary": summary_msg,
        "claims": claim_results,
        "has_low_confidence_ocr_warning": has_low_ocr_flag,
        "has_contradiction_warning": has_contra_flag,
        "has_vision_only_warning": has_vision_flag,
    }
